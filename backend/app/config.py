"""Application settings, loaded from environment / .env (pydantic-settings)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # Look for .env in backend/ first, then the repo root (where it actually lives).
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # Database
    database_url: str

    # LiveKit Cloud
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    # Deepgram
    deepgram_api_key: str
    # STT model + language. "multi" enables multilingual code-switching (e.g. Hindi +
    # English / Hinglish), which needs nova-3. For a single language use e.g. "hi"
    # (Hindi) on nova-2/nova-3, or "en" for English-only.
    deepgram_model: str = "nova-3"
    deepgram_language: str = "multi"

    # Where the full-fidelity meeting recordings (one WAV per call) are written by
    # the bot and read back for the authoritative post-meeting batch transcription.
    recordings_dir: str = "recordings"

    # Gemini. Two ways to authenticate, preferred in this order by llm/gemini_client.py:
    #   - Vertex AI: set gemini_vertex_project + gemini_vertex_credentials_file. No key is
    #     stored here, so rotating one means swapping a single file.
    #   - AI Studio: set gemini_api_key. Simplest for local dev.
    # Model names are identical on both backends, and gemini-embedding-001 returns the
    # same vectors either way, so stored embeddings survive a switch between them.
    gemini_api_key: str | None = None
    gemini_vertex_project: str | None = None
    # Vertex serves models per-region; the model must be available in this location.
    # "global" also works and routes to the nearest region.
    gemini_vertex_location: str = "us-central1"
    # Absolute path to the Vertex service-account JSON. Loaded explicitly (see
    # llm/gemini_client.py) rather than through GOOGLE_APPLICATION_CREDENTIALS, because
    # pydantic-settings parses .env into this object without exporting to os.environ —
    # ADC would not see a value set there, and would fail only outside Docker. Keep it
    # absolute: the app's working directory differs between local runs and the image.
    gemini_vertex_credentials_file: str | None = None
    gemini_llm_model: str = "gemini-2.5-flash"
    gemini_embed_model: str = "gemini-embedding-001"

    # Google Meet REST API (post-meeting transcripts/recordings).
    # Path to a service-account JSON key that has domain-wide delegation on the
    # Workspace. google_impersonate_subject is the Workspace user it acts as
    # (the meeting organizer). No browser / password / 2FA involved.
    google_service_account_file: str | None = None
    google_impersonate_subject: str | None = None

    # Google OAuth (per-user calendar connection — the no-admin way to read a
    # meeting's attendee emails). Create an OAuth 2.0 "Web application" client, add
    # the calendar.readonly scope to the consent screen, and register the redirect
    # URI below on the client. The organizer connects their own calendar once.
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str = "http://localhost:8000/oauth/google/callback"
    # Where to send the browser back to after connecting (the frontend Settings page).
    app_base_url: str = "http://localhost:3000"

    # Bot
    bot_display_name: str = "Notetaker"
    # On a server there is no screen, so a headful Chromium has nowhere to draw and
    # refuses to start. With this on, the bot spawns an Xvfb virtual display (see
    # app/bot/display.py) and points Chromium at it: no window, nothing to see, and
    # Meet still gets the real browser it insists on. Ignored when DISPLAY is already
    # set (your desktop, or a container entrypoint that starts its own Xvfb).
    # Requires the `Xvfb` binary on PATH. Keep this ON in production.
    use_xvfb: bool = True
    # How many meetings the bot can be in at the same time (à la Fireflies/Read.ai).
    # Each concurrent bot runs its own Chromium + audio sink, so size this to the
    # host: roughly 1-1.5 GB RAM and one core per bot is a safe budget, plus ~0.5 GB
    # of /dev/shm and ~0.5 GB of disk per profile slot (see app/bot/profiles.py).
    # 6 needs a host with ~8 cores / 16 GB before anything else runs on it.
    max_concurrent_bots: int = 6
    # Persistent Chromium profile dir. The bot's Google login is stored here, so
    # it stays signed in across runs (sign in once, reuse forever). In prod, put
    # this on a persistent volume / restore it from a secret at startup.
    bot_user_data_dir: str = "bot_profile"
    # True runs Chromium in Playwright's headless mode. Do NOT enable this to hide the
    # window in production — Meet detects headless Chromium, and a headless browser
    # opens no PulseAudio sink-input, so `audio_capture` would record silence. Use
    # `use_xvfb` instead: headful browser, virtual display, nothing rendered anywhere.
    bot_headless: bool = False
    # The bot's Google account credentials. Used to sign in once (inline, in the
    # join window). Email is also the address users add as a meeting participant
    # so the bot is auto-admitted instead of queued/rejected.
    bot_google_account_email: str | None = None
    bot_google_account_password: str | None = None
    # An auto-joined bot that finds itself alone (nobody showed up, or everyone
    # left without removing it) leaves after this long, freeing its slot. The
    # timer only counts successful roster reads showing just the bot; 0 disables
    # and restores the old behaviour (stay until removed / stopped).
    bot_alone_timeout_seconds: int = 600
    # How long the bot keeps knocking before giving up on a meeting it wasn't
    # admitted to (cancelled meeting, nobody showed, or the host ignored it).
    # Invited bots are auto-admitted and never wait this long; this mainly guards
    # meetings auto-joined from a user's connected calendar, where the bot isn't
    # a guest and a human must click Admit.
    bot_admit_timeout_seconds: int = 300

    # --- Calendar auto-join (à la Fireflies / Otter / Read.ai) -----------------
    # Users invite the bot's email to their meetings anyway (that is what gets it
    # auto-admitted), so every meeting sits on the bot account's own calendar.
    # When enabled, a background poller reads that calendar (bot OAuth connection,
    # calendar.readonly scope) and launches a bot as each meeting starts — no one
    # has to paste the Meet link anymore. Requires the bot Google account to be
    # connected in Settings with the calendar scope granted (reconnect once after
    # upgrading to a build that has this feature).
    auto_join_enabled: bool = True
    # How often the bot's calendar is polled for upcoming/changed events.
    auto_join_poll_seconds: int = 60
    # Join this many seconds before the event's scheduled start, so the bot is in
    # the room (or first in the admit queue) when people arrive.
    auto_join_lead_seconds: int = 60
    # How far ahead the poller mirrors events (visibility in the UI schedule).
    auto_join_lookahead_hours: int = 12

    # Participant role classification (our team vs the client). Any attendee whose
    # email domain is in this list is treated as our internal team; everyone else
    # is the client/prospect. Comma-separated in env, e.g. "blostem.com,blostem.ai".
    internal_email_domains: Annotated[list[str], NoDecode] = ["blostem.com"]
    # Our own company name, given to the LLM so it can classify unregistered speakers
    # ("who sells for <us>" vs "who buys") from transcript evidence.
    our_company_name: str = "Blostem"

    # App
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    # Set APP_ENV=production on the server. It doesn't change behaviour on its own —
    # it turns the safety checks in `_check_production_safety` from advice into a
    # refusal to boot. Every unsafe default below is convenient for local dev and
    # dangerous once the app is reachable from the internet.
    app_env: str = "development"

    # --- Authentication -------------------------------------------------------
    # Signing/encryption key for anything the app must keep secret at rest.
    # Generate with `openssl rand -hex 32` and treat it as long-lived.
    secret_key: str
    # How long a session cookie stays valid. Short enough that a stolen laptop stops
    # working within a workday; sessions are revocable server-side regardless.
    session_ttl_hours: int = 12
    # Cookie flags. `secure` MUST be true in production (HTTPS only) — over plain HTTP
    # the session token travels in cleartext. Set to false only for local dev.
    cookie_secure: bool = True
    # "lax" is safe (and CSRF-resistant) when the frontend and API share a registrable
    # domain, e.g. app.blostem.com + api.blostem.com, or localhost:3000 + :8000. If you
    # deploy them on genuinely different sites you must use "none" AND add CSRF tokens.
    # Do NOT use "strict": Google's OAuth callback is a cross-site top-level navigation
    # back to /oauth/google/callback, and strict would withhold the session cookie there,
    # breaking the calendar and bot-account connect flows.
    cookie_samesite: str = "lax"
    # Set to the shared parent domain in production, e.g. ".blostem.com". None keeps
    # the cookie host-only, which is correct for local dev.
    cookie_domain: str | None = None
    # Failed password attempts before the account locks, and for how long.
    max_login_attempts: int = 5
    lockout_minutes: int = 15

    # --- Email one-time codes -------------------------------------------------
    # The second factor: a numeric code mailed to the user on every sign-in, and once
    # more at sign-up to prove the address is really theirs.
    otp_length: int = 6
    # Short-lived by design. A code that outlives the tab it was requested from is
    # just a weaker password sitting in an inbox.
    otp_ttl_minutes: int = 10
    # Wrong codes before the half-authenticated session is destroyed and the user must
    # re-enter their password. Caps guessing at a few tries per password entry.
    max_otp_attempts: int = 5
    # Floor between two sends on one session, so "Resend" can't be used to flood an
    # inbox (or burn the SMTP account's daily quota).
    otp_resend_seconds: int = 60

    # --- SMTP (delivers the one-time codes) -----------------------------------
    # Port 465 is implicit TLS; anything else (587) is STARTTLS. Leave SMTP_HOST unset
    # in development to print codes to the log instead of mailing them.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: str | None = None
    # RFC 5322 From header. A bare address or a "Name <addr>" pair both work.
    smtp_from: str = "Fennec <no-reply@localhost>"

    # Browsers refuse credentialed cross-origin requests to a wildcard origin, so the
    # frontend origins must be listed explicitly. Comma-separated in env.
    # NoDecode: without it pydantic-settings JSON-decodes list fields straight from
    # .env and a comma-separated value raises before any validator can split it.
    cors_allow_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            v = v.split(",")
        if isinstance(v, list):
            return [o.strip().rstrip("/") for o in v if str(o).strip()]
        return v

    @field_validator(
        "bot_google_account_email",
        "bot_google_account_password",
        "bot_user_data_dir",
        "smtp_host",
        "smtp_user",
        "smtp_pass",
        "smtp_from",
        mode="before",
    )
    @classmethod
    def _strip(cls, v):
        # .env values often pick up trailing spaces; a stray space in the bot
        # email silently breaks the Google sign-in, so trim these defensively.
        # An SMTP password with a trailing space fails auth just as quietly.
        return v.strip() if isinstance(v, str) else v

    @field_validator("internal_email_domains", mode="before")
    @classmethod
    def _split_domains(cls, v):
        # Accept a comma-separated string from .env (pydantic would otherwise try to
        # JSON-decode it). Normalize to lowercase, bare domains (no leading '@').
        if isinstance(v, str):
            v = [d for d in v.split(",")]
        if isinstance(v, list):
            return [d.strip().lower().lstrip("@") for d in v if str(d).strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in ("production", "prod")

    @model_validator(mode="after")
    def _check_production_safety(self):
        """Refuse to boot a production server that is configured insecurely.

        Each of these is a default that makes local development pleasant and makes a
        deployed server unsafe. A crash on startup is the cheapest possible time to
        find out — far cheaper than discovering it from an access log.
        """
        if not self.is_production:
            return self

        problems: list[str] = []

        if not self.cookie_secure:
            problems.append(
                "COOKIE_SECURE=false would send session cookies over plain HTTP. Set it to true."
            )
        if self.cookie_samesite.strip().lower() == "none" and not self.cookie_secure:
            problems.append(
                "COOKIE_SAMESITE=none requires COOKIE_SECURE=true (browsers reject it otherwise)."
            )
        if "*" in self.cors_allow_origins:
            problems.append(
                "CORS_ALLOW_ORIGINS cannot be '*' — credentialed requests forbid wildcards."
            )
        if any(
            o.startswith("http://") and "localhost" not in o
            for o in self.cors_allow_origins
        ):
            problems.append(
                "CORS_ALLOW_ORIGINS contains a non-local http:// origin; use https://."
            )
        if len(self.secret_key) < 32:
            problems.append(
                "SECRET_KEY is too short (need >=32 chars). Generate: openssl rand -hex 32"
            )
        if not self.smtp_host:
            problems.append(
                "SMTP_HOST is unset, so login codes would be written to the log instead of "
                "emailed — nobody could sign in. Configure SMTP."
            )
        if self.bot_headless:
            problems.append(
                "BOT_HEADLESS=true breaks meeting capture (Meet detects headless Chromium, and it "
                "opens no PulseAudio stream to record). Use USE_XVFB=true instead."
            )
        if not self.use_xvfb:
            problems.append(
                "USE_XVFB=false leaves the headful browser with no display to draw on. "
                "Set it to true unless a DISPLAY is provided by the host."
            )
        if not self.gemini_vertex_project and not self.gemini_api_key:
            problems.append(
                "Neither GEMINI_VERTEX_PROJECT nor GEMINI_API_KEY is set, so every summary, "
                "MOM and embedding would fail. Set one."
            )
        if self.gemini_vertex_project and self.gemini_vertex_credentials_file:
            if not Path(self.gemini_vertex_credentials_file).is_file():
                problems.append(
                    f"GEMINI_VERTEX_CREDENTIALS_FILE={self.gemini_vertex_credentials_file} does not "
                    "exist, so no LLM call could authenticate. Check the path and any volume mount."
                )

        if problems:
            raise ValueError(
                "APP_ENV=production but the configuration is unsafe:\n  - "
                + "\n  - ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
