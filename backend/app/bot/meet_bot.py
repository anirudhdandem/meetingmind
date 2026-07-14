"""Google Meet join automation via Playwright.

Runs a *headful* Chromium (inside Xvfb on servers) because Meet behaves badly headless and
autoplay/getUserMedia are easier with a real display. The bot joins muted with no camera and
just listens; its audio is captured separately by PulseAudioCapture.

NOTE: Meet's DOM changes regularly. Selectors below use accessible names with fallbacks, but
expect to maintain them — that maintenance is the price of building the bot from scratch.
"""

from __future__ import annotations

import asyncio
import os
import re

from playwright.async_api import BrowserContext, Page, async_playwright

from app.bot.audio_capture import _descendant_pids
from app.bot.display import ensure_display
from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Runs in the page to detect who is speaking right now. Meet's class names are hashed
# and change over time, so this leans on structural/role signals and returns loose
# candidate strings — the server matches them to the known roster. If Meet's DOM
# shifts, this is the ONE place to adjust: run it against a live call in the browser
# console to see what it currently matches.
_ACTIVE_SPEAKER_JS = r"""
() => {
  const found = [];

  // --- Source 1: live captions (Google attributes each line to a speaker name). ---
  // The captions region repeats speaker blocks; the name is the block's leading label.
  const capSel = [
    '[aria-label*="aption" i]',
    '[jsname="dsyhDe"]',
    '[role="region"][aria-label*="aption" i]',
  ];
  for (const sel of capSel) {
    const region = document.querySelector(sel);
    if (!region) continue;
    // Each caption entry typically has a small avatar/name span followed by text.
    // Meet marks the speaker name span with a device/name span; grab short leading
    // text nodes that look like names.
    region.querySelectorAll('span, div').forEach((el) => {
      const t = (el.textContent || '').trim();
      // A name label is short, has no sentence punctuation, and isn't the caption body.
      if (t && t.length <= 40 && !/[.?!,:]/.test(t) && el.children.length === 0) {
        found.push(t);
      }
    });
    if (found.length) break;
  }

  // --- Source 2: speaking tiles (active speaker's tile animates an audio indicator). ---
  // We consider a tile "speaking" if it contains an element whose CSS animation is
  // running (the pulsing sound bars), then read that tile's participant name.
  const tiles = document.querySelectorAll('[data-participant-id]');
  tiles.forEach((tile) => {
    let speaking = false;
    const anims = tile.querySelectorAll('*');
    for (const el of anims) {
      const cs = getComputedStyle(el);
      // The audio-level bars use a running CSS animation while the person speaks.
      if (cs.animationName && cs.animationName !== 'none' &&
          cs.animationPlayState === 'running') {
        speaking = true;
        break;
      }
    }
    if (!speaking) return;
    // Name: prefer an explicit name attribute, else the shortest text line in the tile.
    let name = tile.getAttribute('data-self-name') || '';
    if (!name) {
      const lines = (tile.textContent || '')
        .split('\n').map((s) => s.trim())
        .filter((s) => s && s.length <= 40 && !/[.?!]/.test(s));
      name = lines[0] || '';
    }
    if (name) found.push(name);
  });

  return found;
}
"""

# Flags: auto-accept mic/cam prompts, allow autoplay, look less like automation.
_CHROME_ARGS = [
    "--use-fake-ui-for-media-stream",
    "--autoplay-policy=no-user-gesture-required",
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-sandbox",
    "--start-maximized",
]


class MeetBot:
    def __init__(
        self,
        meeting_url: str,
        display_name: str | None = None,
        user_data_dir: str | None = None,
        headless: bool | None = None,
    ) -> None:
        settings = get_settings()
        self.meeting_url = meeting_url
        self.display_name = display_name or settings.bot_display_name
        # Persistent Chrome profile: the Google login lives here, so the bot
        # stays signed in across runs (one window, no re-login). Realpath'd so
        # it uniquely identifies this bot's Chromium in /proc (browser_pids).
        self.user_data_dir = os.path.realpath(user_data_dir or settings.bot_user_data_dir)
        self.headless = settings.bot_headless if headless is None else headless
        # Normalize: a stray space in the configured email breaks Google sign-in.
        self._email = (settings.bot_google_account_email or "").strip() or None
        self._password = (settings.bot_google_account_password or "").strip() or None
        self._pw = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def browser_pids(self) -> set[int]:
        """PIDs of THIS bot's Chromium process tree, matched by its profile dir.

        With several bots in one process, scoping audio pinning to the API
        process's subtree would sweep every bot's browser into one sink and mix
        the meetings. Chromium's root process carries `--user-data-dir=<profile>`
        on its command line, and the profile dir is unique per bot, so match that
        root and take its whole subtree (audio streams come from child utility
        processes).
        """
        # Trailing space anchors the arg boundary (every \0-terminated arg gains
        # one below), so "slot-1" can't match a "slot-10" profile.
        flag = f"--user-data-dir={self.user_data_dir} "
        pids: set[int] = set()
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as f:
                    cmd = f.read().replace(b"\x00", b" ").decode("utf-8", "replace")
            except OSError:
                continue
            if flag in cmd:
                pids |= _descendant_pids(int(entry))
        return pids

    async def join(self, admit_timeout: float = 120.0) -> None:
        """Sign in (once, if needed) and join the meeting — all in one browser.

        Uses a persistent profile so the Google session is reused on later runs.
        The bot joins as a real signed-in account; users add its email as a
        meeting participant so it's auto-admitted instead of rejected/queued.
        """
        # On a server there is no screen: put the headful browser on a virtual one.
        # Blocking (spawns Xvfb), so keep it off the event loop. No-op once running.
        await asyncio.to_thread(ensure_display)

        self._pw = await async_playwright().start()
        # launch_persistent_context IS the browser+context in one — a single
        # window that keeps its cookies in user_data_dir between runs.
        self._context = await self._pw.chromium.launch_persistent_context(
            self.user_data_dir,
            headless=self.headless,
            args=_CHROME_ARGS,
            permissions=["microphone", "camera"],
            viewport={"width": 1280, "height": 720},
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        page = self._page

        await self._ensure_signed_in(page)

        log.info("Navigating to %s", self.meeting_url)
        # Meet keeps streaming connections open, so it never reaches "networkidle".
        # Wait for the DOM instead; the pre-join controls are awaited individually.
        await page.goto(self.meeting_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)  # let the pre-join UI render

        await self._dismiss_dialogs(page)
        await self._turn_off_devices(page)
        await self._set_name(page)
        await self._click_join(page)
        await self._wait_until_admitted(page, admit_timeout)
        log.info("Bot admitted to the meeting")

    async def _ensure_signed_in(self, page: Page, timeout: float = 180.0) -> None:
        """Guarantee the profile is signed into the *configured* Google account.

        The persistent profile remembers whichever account last signed in, so we
        must check WHICH account is active — not merely that some account is. If it
        doesn't match BOT_GOOGLE_ACCOUNT_EMAIL, we sign out and sign in as the
        configured account. On a CAPTCHA / 'verify it's you', a human clears it once
        (run `python -m scripts.bot_login`); after that this returns fast.
        """
        if not self._email or not self._password:
            log.warning(
                "No BOT_GOOGLE_ACCOUNT_EMAIL/PASSWORD set — Meet will reject the bot anonymously."
            )
            return

        want = self._email.lower()
        current = await self._current_account_email(page)
        if current == want:
            log.info("Bot already signed in as configured account %s", current)
            return

        if current:
            log.warning(
                "Profile is signed in as %s but the configured account is %s — switching.",
                current,
                self._email,
            )
            await self._logout(page)
        else:
            log.info("No matching session; signing in as %s", self._email)

        await self._sign_in_as(page, timeout)

    async def _current_account_email(self, page: Page) -> str | None:
        """Return the email of the account currently signed into the profile, or None."""
        try:
            await page.goto("https://myaccount.google.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
        except Exception:
            return None
        # Bounced to a sign-in / chooser page → no active session.
        if "myaccount.google.com" not in page.url:
            return None
        # The account chip's aria-label embeds the email, e.g.
        # "Google Account: Notetaker (blostem3@gmail.com)".
        for sel in ('a[aria-label*="@"]', '[aria-label*="@gmail.com"]', '[aria-label*="@"]'):
            try:
                loc = page.locator(sel)
                for i in range(min(await loc.count(), 6)):
                    label = await loc.nth(i).get_attribute("aria-label")
                    m = _EMAIL_RE.search(label or "")
                    if m:
                        return m.group(0).lower()
            except Exception:
                continue
        return None

    async def _logout(self, page: Page) -> None:
        """Sign all accounts out of the persistent profile."""
        try:
            await page.goto("https://accounts.google.com/Logout", wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
        except Exception:
            log.debug("logout navigation issue", exc_info=True)

    async def _sign_in_as(self, page: Page, timeout: float) -> None:
        """Sign in as the configured account, handling the 'choose an account' chooser."""
        email, password = self._email, self._password
        assert email and password
        try:
            await page.goto(
                "https://accounts.google.com/ServiceLogin?continue=https://myaccount.google.com/",
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(1200)
        except Exception:
            log.debug("sign-in navigation issue", exc_info=True)

        # If Google shows remembered accounts, force the email form.
        for name in ("Use another account", "Add account"):
            try:
                el = page.get_by_text(name, exact=False).first
                if await el.is_visible(timeout=1500):
                    await el.click(timeout=2000)
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                continue

        log.info("Signing in as %s", email)
        try:
            await page.fill("#identifierId", email, timeout=15000)
            await page.click("#identifierNext", timeout=5000)
            await page.wait_for_selector('input[type="password"]', state="visible", timeout=15000)
            await page.fill('input[type="password"]', password)
            await page.click("#passwordNext", timeout=5000)
        except Exception as e:
            log.warning("Auto-fill incomplete (%s) — finish any challenge in the window", e)

        want = email.lower()
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if "myaccount.google.com" in page.url and "signin" not in page.url:
                current = await self._current_account_email(page)
                if current is None or current == want:
                    log.info("Signed in as %s", email)
                    return
                # Signed into the wrong account again (e.g. chooser picked it) — retry once.
                log.warning("Signed in as %s, not %s — retrying after logout", current, email)
                await self._logout(page)
                return await self._sign_in_as(page, timeout / 2)
            await asyncio.sleep(3)
        log.warning("Sign-in as %s not confirmed before timeout; continuing anyway", email)

    async def _dismiss_dialogs(self, page: Page) -> None:
        for label in ("Dismiss", "Got it", "No thanks", "Continue without microphone"):
            try:
                await page.get_by_role("button", name=label).click(timeout=1500)
            except Exception:
                pass

    async def _turn_off_devices(self, page: Page) -> None:
        # Join muted + camera off. Toggles vary; try aria labels, ignore if already off.
        for label in ("Turn off microphone", "Turn off camera"):
            try:
                await page.get_by_role("button", name=label).click(timeout=1500)
            except Exception:
                pass

    async def _set_name(self, page: Page) -> None:
        # Only present when not signed into a Google account.
        try:
            box = page.get_by_label("Your name")
            await box.fill(self.display_name, timeout=3000)
            log.info("Set display name: %s", self.display_name)
        except Exception:
            log.info("No name field (likely signed-in session)")

    async def _click_join(self, page: Page) -> None:
        for label in ("Ask to join", "Join now"):
            try:
                await page.get_by_role("button", name=label).click(timeout=4000)
                log.info("Clicked '%s'", label)
                return
            except Exception:
                continue
        raise RuntimeError("Could not find a join button on the Meet page")

    # Any of these signals "we are inside the call". Meet's UI varies (A/B rollouts,
    # compact layouts collapse the toolbar behind a "Call controls" overflow), so
    # admission and removal detection MUST use the same list — checking a narrower
    # set on removal is how the bot once left every meeting 10s after joining.
    _IN_CALL_CONTROLS = ("Leave call", "End call", "Call controls")

    async def _sees_in_call_controls(self, page: Page) -> str | None:
        """The first visible in-call control's label, or None when none are found."""
        for label in self._IN_CALL_CONTROLS:
            try:
                if await page.get_by_role("button", name=label).first.is_visible(
                    timeout=500
                ):
                    return label
            except Exception:
                pass
        return None

    async def _wait_until_admitted(self, page: Page, timeout: float) -> None:
        """Poll for an in-call control (e.g. 'Leave call') signalling admission."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            label = await self._sees_in_call_controls(page)
            if label is not None:
                log.info("Admission detected via %r control", label)
                return
            await asyncio.sleep(2)
        raise TimeoutError("Bot was not admitted before timeout (host must let it in)")

    async def wait_until_removed(self, poll: float = 3.0) -> None:
        """Block until the bot is no longer in the call (host kicked it / it ended).

        Stays in the meeting indefinitely otherwise. Detects removal via Meet's
        'removed / return to home' screen, or the in-call 'Leave call' control
        disappearing for two consecutive polls.
        """
        page = self._page
        assert page is not None
        removal_texts = (
            "Return to home screen",
            "You've been removed",
            "You were removed",
            "removed from the meeting",
            "You left the meeting",
            "The meeting has ended",
            "call has ended",
            "Your host ended the call",
            "Rejoin",
        )
        misses = 0
        while True:
            for text in removal_texts:
                try:
                    if await page.get_by_text(text, exact=False).first.is_visible(timeout=500):
                        log.info("Bot removed from meeting (saw %r)", text)
                        return
                except Exception:
                    pass
            # Same control set as admission — see _IN_CALL_CONTROLS. Several
            # consecutive misses guard against dialogs/animations briefly covering
            # the toolbar; a real removal also shows one of the texts above.
            visible = await self._sees_in_call_controls(page) is not None
            misses = 0 if visible else misses + 1
            if misses >= 4:
                await self._debug_snapshot(page, "removed-detector")
                log.info("In-call controls gone for %d polls; assuming bot was removed", misses)
                return
            await asyncio.sleep(poll)

    async def _debug_snapshot(self, page: Page, tag: str) -> None:
        """Best-effort screenshot + URL log, for post-mortems of detector decisions."""
        try:
            log.info("debug snapshot (%s): url=%s title=%r", tag, page.url, await page.title())
            path = os.path.join(get_settings().recordings_dir, f"debug-{tag}.png")
            await page.screenshot(path=path, timeout=3000)
            log.info("debug snapshot saved -> %s", path)
        except Exception:
            log.debug("debug snapshot failed", exc_info=True)

    async def _open_people_panel(self, page: Page) -> None:
        """Open the People/roster side panel if it isn't already open (best-effort)."""
        for label in ("People", "Show everyone", "Participants"):
            try:
                btn = page.get_by_role("button", name=label)
                if await btn.is_visible(timeout=600):
                    await btn.click(timeout=1200)
                    await page.wait_for_timeout(800)  # let the panel render
                    return
            except Exception:
                continue

    async def get_participants(self) -> list[str]:
        """Best-effort read of the Meet roster (participant display names).

        Reads the People panel so attendees come from the real participant list rather
        than diarization guesses. Meet's DOM is obfuscated and changes often, so we open
        the panel proactively and try several role/aria strategies, returning whatever we
        can — empty list on failure (the caller falls back to LLM-inferred attendees).
        """
        page = self._page
        if page is None:
            return []

        # Each entry: (selector, source) — "text" reads inner_text, "aria" reads the
        # aria-label attribute (Meet often labels a participant row with the person's name).
        strategies = (
            ('[role="list"] [role="listitem"]', "text"),
            ('[aria-label="Participants"] [role="listitem"]', "text"),
            ("div[data-participant-id]", "aria"),
            ("[data-participant-id]", "text"),
            ('div[role="listitem"][aria-label]', "aria"),
        )

        def _clean(raw: str | None) -> str:
            if not raw:
                return ""
            # Roster rows often pack name + status onto separate lines; take the name line.
            name = raw.splitlines()[0].strip()
            # aria-labels sometimes read "Alice Smith, muted" — keep the leading name.
            return name.split(",")[0].strip()

        async def _read() -> set[str]:
            found: set[str] = set()
            for sel, source in strategies:
                try:
                    loc = page.locator(sel)
                    count = await loc.count()
                    for i in range(count):
                        item = loc.nth(i)
                        raw = (
                            await item.get_attribute("aria-label")
                            if source == "aria"
                            else await item.inner_text()
                        )
                        name = _clean(raw)
                        if name and len(name) <= 60:
                            found.add(name)
                    if found:
                        break
                except Exception:
                    continue
            return found

        try:
            await self._open_people_panel(page)
            names = await _read()

            noise = {
                self.display_name, "Notetaker", "You", "Contributors",
                "In call", "Search for people", "Add people", "Participants", "",
            }
            return sorted(n for n in names if n not in noise)
        except Exception:
            log.debug("get_participants failed", exc_info=True)
            return []

    async def enable_captions(self) -> None:
        """Turn on Meet live captions (best-effort).

        Captions are our most reliable ground-truth speaker signal: Google itself
        attributes each caption line to a participant's real name. We only read the
        *names* off them (Deepgram still provides the actual text), so caption quality
        doesn't matter — only that a name is attached to speech at a given moment.
        Pressing 'c' is the documented Meet shortcut; we also try the button.
        """
        page = self._page
        if page is None:
            return
        try:
            for label in ("Turn on captions", "Captions"):
                try:
                    btn = page.get_by_role("button", name=label)
                    if await btn.is_visible(timeout=800):
                        await btn.click(timeout=1500)
                        log.info("Enabled captions via '%s'", label)
                        return
                except Exception:
                    continue
            # Fallback: keyboard shortcut.
            await page.keyboard.press("c")
            log.info("Enabled captions via keyboard shortcut")
        except Exception:
            log.debug("enable_captions failed (non-fatal)", exc_info=True)

    async def get_active_speakers(self) -> list[str]:
        """Best-effort read of who is speaking *right now* (participant display names).

        Two sources, both of which Meet maintains itself:
          1. Live captions — each caption block is prefixed with the speaker's name.
          2. Speaking tiles — the active speaker's video tile shows an animated
             audio indicator; that tile carries the participant's name.

        Meet's DOM is obfuscated and changes, so the browser side stays deliberately
        loose: it returns whatever candidate name strings it can see. The server
        (speaker_attribution) matches those against the known roster, so a noisy
        candidate like "Artha Vault is speaking" still resolves to "Artha Vault".
        Returns [] on any failure — the pipeline then falls back to LLM naming, so a
        broken selector degrades gracefully instead of corrupting attribution.
        """
        page = self._page
        if page is None:
            return []
        try:
            names = await page.evaluate(_ACTIVE_SPEAKER_JS)
        except Exception:
            log.debug("get_active_speakers evaluate failed", exc_info=True)
            return []
        out: list[str] = []
        seen: set[str] = set()
        for raw in names or []:
            name = (raw or "").splitlines()[0].strip() if raw else ""
            low = name.lower()
            if name and len(name) <= 60 and low not in seen and name != self.display_name:
                seen.add(low)
                out.append(name)
        return out

    async def leave(self) -> None:
        if self._page is not None:
            try:
                await self._page.get_by_role("button", name="Leave call").click(timeout=3000)
            except Exception:
                pass
        if self._context is not None:
            await self._context.close()
        if self._pw is not None:
            await self._pw.stop()
        log.info("Bot left the meeting")
