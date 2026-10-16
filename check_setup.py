"""Check local configuration and assets without contacting Telegram/AniList."""

import os
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
from manual_colors import load, normalize_color
from poster import font, get_footer
from publishing import load_channel

ROOT = Path(__file__).resolve().parent


def check():
    load_dotenv(ROOT / ".env")
    errors = []
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token.startswith("PASTE_") or ":" not in token:
        errors.append("Replace the BOT_TOKEN placeholder in .env.")
    try:
        ids = {int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()}
        if not ids or any(x <= 0 for x in ids):
            errors.append("Set ALLOWED_USER_IDS to positive Telegram user IDs. /id can find yours.")
    except ValueError:
        errors.append("ALLOWED_USER_IDS must be numeric IDs separated by commas.")
    if os.getenv("SEND_PNG", "true").lower() not in {"true", "false", "1", "0", "yes", "no"}:
        errors.append("SEND_PNG must be true or false.")
    try:
        font(20)
        font(20, True)
        for name in ["logo.jpg", "mangabay-logo.jpg"]:
            with Image.open(ROOT / "assets" / name) as image:
                image.verify()
        for color in load().values():
            normalize_color(color)
        load_channel()
        get_footer("ANIME")
        get_footer("MANGA")
    except (OSError, ValueError) as exc:
        # Do not print file contents or credential values from local settings.
        errors.append(
            f"Asset or saved-settings check failed ({type(exc).__name__}); check assets/ and data/ JSON files."
        )
    return errors


def main():
    errors = check()
    if errors:
        for error in errors:
            print("- " + error)
        raise SystemExit(1)
    print("Local configuration, fonts, logos and saved settings: OK.")
    print("This is an offline check; test Telegram delivery and source access on the VPS.")


if __name__ == "__main__":
    main()
