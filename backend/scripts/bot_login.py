import asyncio
import shutil
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from app.bot.meet_bot import _CHROME_ARGS, MeetBot
from app.config import get_settings


async def main() -> None:
    s = get_settings()
    email = (s.bot_google_account_email or "").strip()
    password = (s.bot_google_account_password or "").strip()
    if not email or not password:
        raise SystemExit("Set BOT_GOOGLE_ACCOUNT_EMAIL and BOT_GOOGLE_ACCOUNT_PASSWORD in .env")

    if "--reset" in sys.argv:
        prof = Path(s.bot_user_data_dir)
        if prof.exists():
            shutil.rmtree(prof, ignore_errors=True)
            print(f"🧹 wiped profile {prof}")

    print(f"Target account: {email}")
    bot = MeetBot("about:blank")  # we only use its sign-in logic here

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            s.bot_user_data_dir,
            headless=False,
            args=_CHROME_ARGS,
            viewport={"width": 1280, "height": 720},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Reuse the exact account-aware logic the live bot uses (verify-or-switch).
        await bot._ensure_signed_in(page, timeout=240.0)

        final = await bot._current_account_email(page)
        if final == email.lower():
            print(f"✅ SIGNED IN as {final} — session saved to {s.bot_user_data_dir}")
        else:
            print(
                f"❌ profile is on {final or 'no account'}, expected {email}. "
                "Re-run and clear any Google challenge within the window."
            )
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
