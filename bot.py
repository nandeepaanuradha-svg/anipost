"""Animebay Telegram poster bot. Run: python bot.py"""

import asyncio
import copy
import time
import traceback
from PIL import Image, ImageOps
import io
import logging
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from anilist import AniList, SourceError
from poster import render, caption, title, utf16_len
import publishing
import manual_colors
from telegram_output import edit_status, photo_details, reply_details
from manga_api import MangaList
import manga_poster

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
LOG = logging.getLogger("anipost")
ALLOWED = set()
HELP = (
    "Send an anime name, for example:\n/anime Frieren\n\n"
    "Choose the correct title from the results. You receive a poster and Animebay details, "
    "with the synopsis only on the image.\n\n"
    "/manga One Piece — find manga and create a Mangabay post\n"
    "/setimage — change the latest poster image; also works as a photo caption\n"
    "/cancelimage — cancel a waiting image change\n"
    "/post 154587 — use an AniList anime ID\n"
    "/color orange — named color or /color #ff7a18 for any RGB shade\n"
    "/colors — list all color names\n"
    "/languages Japanese | English subtitles — set your own caption label\n"
    "/languages reset — restore the configured label\n"
    "/setchannel @YourChannel — set your main channel\n"
    "/publish https://your-link — preview and publish your latest poster\n"
    "/id — show your Telegram user ID\n/help — show these instructions"
)


def permitted(update):
    return bool(update.effective_user and update.effective_user.id in ALLOWED)


async def access(update):
    if permitted(update):
        return True
    if update.callback_query:
        await update.callback_query.answer("This bot is private.", show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text(
            "This bot is private. Use /id and add your ID to ALLOWED_USER_IDS in .env."
        )
    return False


async def identify(update, context):
    if update.effective_user:
        await update.effective_message.reply_text(f"Your Telegram user ID: {update.effective_user.id}")


async def help_command(update, context):
    if await access(update):
        await update.effective_message.reply_text(HELP)


async def languages(update, context):
    if not await access(update):
        return
    value = " ".join(context.args).strip()
    if not value:
        value = context.user_data.get("languages", os.getenv("LANGUAGES", "Not specified"))
        await update.effective_message.reply_text(
            f"Current label: {value}\nSet it with /languages Japanese | English subtitles"
        )
        return
    if len(value) > 70:
        await update.effective_message.reply_text("Please keep the language label under 71 characters.")
        return
    if value.lower() == "reset":
        context.user_data.pop("languages", None)
    else:
        context.user_data["languages"] = value
    await update.effective_message.reply_text(
        "Language label updated for this session. Use LANGUAGES in .env to keep it after restarts."
    )


async def show_post(message, user_data, context, ident, *, custom_image=None, saved=None, kind="ANIME"):
    kind = saved.get("kind", "ANIME") if saved else kind
    brand = "Mangabay" if kind == "MANGA" else "Animebay"
    renderer = manga_poster.render if kind == "MANGA" else render
    make_caption = manga_poster.caption if kind == "MANGA" else caption
    status = await message.reply_text(f"Getting artwork and building your {brand} post…")
    try:
        api = context.bot_data["manga_api" if kind == "MANGA" else "api"]
        media = copy.deepcopy(saved["media"]) if saved else copy.deepcopy(await api.get(ident))
        media["_poster_color"] = manual_colors.get_color(message.chat_id)
        async with context.bot_data["render_slots"]:
            if custom_image is not None:
                cover, banner = custom_image, None
            else:
                cover_info = media.get("coverImage") or {}
                cover, banner = await asyncio.gather(
                    api.image(cover_info.get("extraLarge") or cover_info.get("large")),
                    api.image(media.get("bannerImage")),
                )
                if not cover and cover_info.get("large") and cover_info.get("large") != cover_info.get("extraLarge"):
                    cover = await api.image(cover_info["large"])
            png = await asyncio.to_thread(renderer, media, cover, banner)
        text = (
            saved["caption"]
            if saved
            else make_caption(media, user_data.get("languages", os.getenv("LANGUAGES", "Not specified")))
        )
    except SourceError as exc:
        await edit_status(status, str(exc))
        return False
    except (OSError, ValueError):
        LOG.warning("Poster processing failed (%s %s)", kind, ident)
        await edit_status(
            status, "The poster could not be processed. Check the artwork, color settings and footer, then try again."
        )
        return False
    buttons = InlineKeyboardMarkup(
        [[InlineKeyboardButton("View on AniList", url=f"https://anilist.co/{kind.lower()}/{ident}")]]
    )
    photo = io.BytesIO(png)
    photo.name = f"{brand.lower()}-{ident}.png"
    try:
        sent_photo = await message.reply_photo(
            photo, **photo_details(text), reply_markup=buttons, write_timeout=60, read_timeout=60
        )
    except TelegramError as exc:
        LOG.warning("Poster photo delivery uncertain (%s)", type(exc).__name__)
        await edit_status(
            status, "Telegram did not confirm photo delivery. Check whether the poster arrived before trying again."
        )
        return False
    LOG.info("Poster sent (%s ID %s)", kind, ident)
    publishing.remember_post(user_data, sent_photo, text, title(media))
    targets = user_data.setdefault("image_targets", {})
    targets[message.chat_id] = {"id": ident, "kind": kind, "media": copy.deepcopy(media), "caption": text}
    while len(targets) > 10:
        targets.pop(next(iter(targets)))
    user_data.pop("image_pending", None)
    if custom_image is not None:
        user_data.pop("publish_pending", None)
    notes = []
    if utf16_len(text) > 1024:
        try:
            await reply_details(message, text)
        except TelegramError as exc:
            LOG.warning("Separate details failed (%s)", type(exc).__name__)
            notes.append("The photo arrived, but the separate details could not be sent.")
    if os.getenv("SEND_PNG", "true").lower() in {"true", "1", "yes"}:
        original = io.BytesIO(png)
        original.name = photo.name
        try:
            await message.reply_document(
                original, caption=f"Original PNG • SL {brand}", write_timeout=60, read_timeout=60
            )
        except TelegramError as exc:
            LOG.warning("Optional PNG failed (%s)", type(exc).__name__)
            notes.append("The photo arrived, but the original PNG could not be sent.")
    await edit_status(
        status,
        "\n".join(
            notes
            + [
                "Ready. Send a picture with /setimage as its caption to change the artwork. "
                "Use /publish YOUR_DOWNLOAD_LINK to preview this version. /color changes your next poster."
            ]
        ),
    )
    return True


MAX_IMAGE_BYTES = 12 * 1024 * 1024


def prepare_image(raw):
    """Validate an uploaded bitmap and normalize size, orientation and transparency."""
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Please send an image smaller than 12 MB.")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"} or getattr(source, "is_animated", False):
                raise ValueError("Please send a still JPG, PNG or WebP image.")
            if source.width * source.height > 24_000_000:
                raise ValueError("Please send an image under 24 megapixels.")
            picture = ImageOps.exif_transpose(source).convert("RGBA")
            picture.thumbnail((3000, 3000), Image.Resampling.LANCZOS)
            flattened = Image.new("RGB", picture.size, (11, 12, 19))
            flattened.paste(picture, mask=picture.getchannel("A"))
            output = io.BytesIO()
            flattened.save(output, "JPEG", quality=95)
            return output.getvalue()
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("That file could not be read as an image. Send a JPG, PNG or WebP.") from exc


def attached_image(message):
    if message.photo:
        return message.photo[-1]
    if message.document:
        return message.document
    return None


async def cancelimage(update, context):
    if not await access(update):
        return
    pending = context.user_data.get("image_pending")
    if pending and pending["chat_id"] == update.effective_message.chat_id:
        context.user_data.pop("image_pending", None)
    await update.effective_message.reply_text("Image-change request cancelled.")


async def setimage(update, context):
    if not await access(update):
        return
    message = update.effective_message
    if context.user_data.get("busy"):
        await message.reply_text("Please wait for your current poster request to finish.")
        return
    uploaded = attached_image(message)
    caption_command = re.match(r"^/setimage(?:@([A-Za-z0-9_]+))?(?:\s|$)", message.caption or "", re.I)
    if caption_command and caption_command[1] and caption_command[1].lower() != context.bot.username.lower():
        return
    text_command = re.match(r"^/setimage(?:@([A-Za-z0-9_]+))?(?:\s|$)", message.text or "", re.I)
    if text_command and text_command[1] and text_command[1].lower() != context.bot.username.lower():
        return
    explicit = bool(caption_command or text_command)
    pending = context.user_data.get("image_pending")
    if pending and (pending["chat_id"] != message.chat_id or pending["expires"] < time.monotonic()):
        pending = None
    if context.user_data.get("image_pending") and pending is None:
        context.user_data.pop("image_pending", None)
    if not explicit and not pending:
        await message.reply_text(
            "To use this picture, reply to it with /setimage after generating an anime or manga poster."
        )
        return
    target = context.user_data.get("image_targets", {}).get(message.chat_id) if explicit else pending["target"]
    if not target:
        await message.reply_text(
            "Generate a poster here first with /anime or /manga, then send your picture with /setimage as its caption."
        )
        return
    if not uploaded and message.reply_to_message:
        # Do not accidentally use a completed poster as replacement cover art.
        key = f"{message.reply_to_message.chat_id}:{message.reply_to_message.message_id}"
        if key not in context.user_data.get("poster_posts", {}):
            uploaded = attached_image(message.reply_to_message)
    if not uploaded:
        context.user_data["image_pending"] = {
            "chat_id": message.chat_id,
            "target": copy.deepcopy(target),
            "expires": time.monotonic() + 600,
        }
        await message.reply_text(
            f"Send one replacement picture for {title(target['media'])}. "
            "You have 10 minutes. Send /cancelimage to cancel."
        )
        return
    if uploaded.file_size and uploaded.file_size > MAX_IMAGE_BYTES:
        await message.reply_text("Please send an image smaller than 12 MB.")
        return
    context.user_data["busy"] = True
    try:
        remote = await uploaded.get_file()
        if remote.file_size and remote.file_size > MAX_IMAGE_BYTES:
            raise ValueError("Please send an image smaller than 12 MB.")
        raw = await remote.download_as_bytearray(read_timeout=60)
        picture = await asyncio.to_thread(prepare_image, bytes(raw))
        await show_post(message, context.user_data, context, target["id"], custom_image=picture, saved=target)
    except ValueError as exc:
        await message.reply_text(str(exc))
    except TelegramError:
        await message.reply_text(
            "Telegram could not complete the image update. Check whether a new poster arrived before trying again."
        )
    finally:
        context.user_data["busy"] = False


async def search(update, context, kind="ANIME"):
    if not await access(update):
        return
    value = update.effective_message.text or ""
    text = " ".join(context.args) if value.startswith("/") else value
    text = text.strip()
    if not text:
        await update.effective_message.reply_text(f"Try /{kind.lower()} followed by a title.")
        return
    if context.user_data.get("busy"):
        await update.effective_message.reply_text("Please wait for your current request to finish.")
        return
    context.user_data["busy"] = True
    try:
        match = re.fullmatch(rf"(?:https?://(?:www\.)?anilist\.co/{kind.lower()}/)?(\d+)(?:/[^\s]*)?", text)
        if match:
            await show_post(update.effective_message, context.user_data, context, int(match[1]), kind=kind)
            return
        if len(text) > 160:
            await update.effective_message.reply_text("Please use a title shorter than 161 characters.")
            return
        choices = await context.bot_data["manga_api" if kind == "MANGA" else "api"].search(text)
        if not choices:
            await update.effective_message.reply_text("No available titles matched. Try the English or Japanese title.")
            return
        uid = update.effective_user.id
        rows = []
        for m in choices:
            year = (m.get("startDate") or {}).get("year") or "TBA"
            label = f"{title(m)[:65]} · {year} · {m.get('format') or 'Anime'}"
            rows.append([InlineKeyboardButton(label, callback_data=f"pick:{uid}:{m['id']}:{kind}")])
        await update.effective_message.reply_text(
            "Choose the manga:" if kind == "MANGA" else "Choose the anime / season:",
            reply_markup=InlineKeyboardMarkup(rows),
        )
    except SourceError as exc:
        await update.effective_message.reply_text(str(exc))
    finally:
        context.user_data["busy"] = False


async def manga(update, context):
    await search(update, context, kind="MANGA")


async def pick(update, context):
    if not await access(update):
        return
    query = update.callback_query
    parts = query.data.split(":")
    _, owner, ident = parts[:3]
    kind = parts[3] if len(parts) == 4 else "ANIME"
    if int(owner) != update.effective_user.id:
        await query.answer("Please run your own search.", show_alert=True)
        return
    if context.user_data.get("busy"):
        await query.answer("Please wait for your current request.", show_alert=True)
        return
    context.user_data["busy"] = True
    try:
        await query.answer("Creating your post…")
        await show_post(query.message, context.user_data, context, int(ident), kind=kind)
    finally:
        context.user_data["busy"] = False


async def on_error(update, context):
    # Avoid exception text/HTTP URLs, which can contain bot tokens.
    frames = traceback.extract_tb(context.error.__traceback__)
    location = " > ".join(f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in frames[-5:])
    LOG.error("Update failed (%s) at %s", type(context.error).__name__, location or "unknown")
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "The request could not finish. Please try again. If this repeats, check the VPS logs."
            )
        except TelegramError:
            pass


async def startup(app):
    app.bot_data["api"] = AniList()
    app.bot_data["manga_api"] = MangaList(app.bot_data["api"])
    app.bot_data["render_slots"] = asyncio.Semaphore(2)
    try:
        await app.bot.set_my_commands(
            [
                BotCommand("anime", "Find an anime and create a post"),
                BotCommand("manga", "Find manga and create a Mangabay post"),
                BotCommand("post", "Create a post by AniList ID"),
                BotCommand("setimage", "Change the latest poster picture"),
                BotCommand("cancelimage", "Cancel a pending picture change"),
                BotCommand("languages", "Set the caption language label"),
                BotCommand("color", "Choose any poster color"),
                BotCommand("colors", "List all color names"),
                BotCommand("setchannel", "Set the main channel"),
                BotCommand("publish", "Preview and publish a poster with a download link"),
                BotCommand("id", "Show your Telegram ID"),
                BotCommand("help", "Show help"),
            ]
        )
    except TelegramError as exc:
        LOG.warning("Could not refresh Telegram command menu (%s)", type(exc).__name__)


async def shutdown(app):
    if "api" in app.bot_data:
        await app.bot_data["api"].close()


def main():
    global ALLOWED
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token.startswith("PASTE_"):
        raise SystemExit("Add your BotFather BOT_TOKEN to .env first.")
    try:
        ALLOWED = {int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()}
    except ValueError:
        raise SystemExit("ALLOWED_USER_IDS must contain numeric IDs separated by commas.") from None
    if not ALLOWED:
        LOG.warning("No users configured. Only /id is available until ALLOWED_USER_IDS is set.")
    app = Application.builder().token(token).concurrent_updates(4).post_init(startup).post_shutdown(shutdown).build()
    publishing.register(app, access)
    manual_colors.register(app, access)
    app.add_handler(CommandHandler("id", identify))
    app.add_handler(CommandHandler(["start", "help"], help_command))
    app.add_handler(CommandHandler("languages", languages))
    app.add_handler(CommandHandler("setimage", setimage))
    app.add_handler(CommandHandler("cancelimage", cancelimage))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, setimage))
    app.add_handler(CommandHandler(["anime", "post"], search))
    app.add_handler(CommandHandler("manga", manga))
    app.add_handler(CallbackQueryHandler(pick, pattern=r"^pick:\d+:\d+(?::(?:ANIME|MANGA))?$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))
    app.add_error_handler(on_error)
    LOG.info("Starting AniPost — anime and manga poster bot")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
