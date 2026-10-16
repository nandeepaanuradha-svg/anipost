"""Channel publishing with a preview, permission checks and one-use confirmation."""

import logging
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import CommandHandler, CallbackQueryHandler
from poster import utf16_len
from storage import read_json, write_json
from telegram_output import photo_details, reply_details, send_details

SETTINGS = Path(__file__).resolve().parent / "data" / "channel.json"
BUTTON = "🔥 Click Here To Download 🔥"
LOG = logging.getLogger("anipost")


def normalize_link(value):
    return "https://" + value if value.lower().startswith("t.me/") else value


async def edit_confirmation(query, text):
    try:
        await query.edit_message_text(text)
    except TelegramError as exc:
        LOG.info("Confirmation status edit skipped (%s)", type(exc).__name__)


def valid_link(url):
    url = normalize_link(url) if isinstance(url, str) else url
    if not url or len(url) > 2048 or any(c.isspace() or ord(c) < 32 for c in url):
        return False
    try:
        p = urlsplit(url)
        return p.scheme in {"https", "http"} and bool(p.hostname) and not p.username and not p.password and p.port != 0
    except ValueError:
        return False


def load_channel():
    value = read_json(SETTINGS, None)
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("id"), int) or not value.get("title"):
        raise ValueError("Invalid channel.json; expected channel id and title.")
    return value


def save_channel(value):
    write_json(SETTINGS, value)


async def check_channel(bot, chat_id, user_id):
    chat = await bot.get_chat(chat_id)
    if chat.type != "channel":
        raise ValueError("Please choose a Telegram channel, not a group.")
    own = await bot.get_chat_member(chat.id, bot.id)
    if own.status != "administrator" or not own.can_post_messages:
        raise ValueError("Add this bot as a channel administrator with Post Messages enabled.")
    member = await bot.get_chat_member(chat.id, user_id)
    if member.status != "creator" and not (member.status == "administrator" and member.can_post_messages):
        raise ValueError("You must be the channel owner or an administrator who can post messages.")
    return {"id": chat.id, "title": chat.title or str(chat.id)}


def remember_post(user_data, message, text, anime_title):
    post = {
        "file_id": message.photo[-1].file_id,
        "caption": text,
        "title": anime_title,
        "chat_id": message.chat_id,
        "message_id": message.message_id,
    }
    posts = user_data.setdefault("poster_posts", {})
    key = f"{message.chat_id}:{message.message_id}"
    posts[key] = post
    while len(posts) > 20:
        posts.pop(next(iter(posts)))
    user_data["last_poster"] = post


def register(app, access):
    async def setchannel(update, context):
        if not await access(update):
            return
        if not context.args:
            current = load_channel()
            await update.effective_message.reply_text(
                (f"Current channel: {current['title']} ({current['id']})\n" if current else "")
                + "Set it with /setchannel @YourChannel or /setchannel -1001234567890. "
                "Add this bot as an admin with Post Messages first."
            )
            return
        target = context.args[0]
        if re.fullmatch(r"-100\d+", target):
            target = int(target)
        elif not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", target):
            await update.effective_message.reply_text(
                "Use @channelusername or its numeric -100… ID. Invite links are not channel IDs."
            )
            return
        try:
            value = await check_channel(context.bot, target, update.effective_user.id)
            save_channel(value)
            await update.effective_message.reply_text(
                f"Main channel saved: {value['title']} ({value['id']}).\nGenerate a poster, then use /publish YOUR_DOWNLOAD_LINK."
            )
        except ValueError as exc:
            await update.effective_message.reply_text(str(exc))
        except TelegramError:
            await update.effective_message.reply_text(
                "Could not verify the channel. Check its username/ID and the bot’s admin permissions."
            )

    async def publish(update, context):
        if not await access(update):
            return
        message = update.effective_message
        if len(context.args) == 1:
            context.args[0] = normalize_link(context.args[0])
        if len(context.args) != 1 or not valid_link(context.args[0]):
            await message.reply_text(
                "Usage: /publish https://t.me/your_download_link\nSend it after creating a poster, or reply to one of your recent poster photos. Only HTTP/HTTPS links are supported."
            )
            return
        channel = load_channel()
        if not channel:
            await message.reply_text("First configure your main channel with /setchannel @YourChannel.")
            return
        reply = message.reply_to_message
        post = (
            context.user_data.get("poster_posts", {}).get(f"{reply.chat_id}:{reply.message_id}")
            if reply
            else context.user_data.get("last_poster")
        )
        if not post or post["chat_id"] != message.chat_id:
            await message.reply_text(
                "Please generate the poster here again, then send /publish with its link. Posters are remembered for the current bot session."
            )
            return
        try:
            channel = await check_channel(context.bot, channel["id"], update.effective_user.id)
        except ValueError as exc:
            await message.reply_text(str(exc))
            return
        except TelegramError:
            await message.reply_text("Channel access could not be verified. Check the bot’s permissions and try again.")
            return
        nonce = secrets.token_hex(8)
        pending = {
            "nonce": nonce,
            "post": dict(post),
            "channel": channel,
            "url": context.args[0],
            "expires": time.monotonic() + 900,
            "chat_id": message.chat_id,
        }
        # Freeze title, image, details, channel and URL in this particular draft.
        context.user_data["publish_pending"] = pending
        await message.reply_photo(
            post["file_id"],
            **photo_details(post["caption"]),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON, url=pending["url"])]]),
        )
        if utf16_len(post["caption"]) > 1024:
            await reply_details(message, post["caption"])
        owner = update.effective_user.id
        await message.reply_text(
            f"Publish {post['title']} to {channel['title']} ({channel['id']})?\n\nDownload link: {pending['url']}\n\n"
            "The preview above is what will be sent. Confirmation expires in 15 minutes.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Publish", callback_data=f"pub:yes:{owner}:{nonce}"),
                        InlineKeyboardButton("Cancel", callback_data=f"pub:no:{owner}:{nonce}"),
                    ]
                ]
            ),
        )

    async def confirm(update, context):
        if not await access(update):
            return
        query = update.callback_query
        _, action, owner, nonce = query.data.split(":")
        if int(owner) != update.effective_user.id:
            await query.answer("Only the person who prepared this post can confirm it.", show_alert=True)
            return
        pending = context.user_data.get("publish_pending")
        if (
            not pending
            or pending["nonce"] != nonce
            or pending["expires"] < time.monotonic()
            or pending["chat_id"] != query.message.chat_id
        ):
            await query.answer("This confirmation expired or was already used. Send /publish again.", show_alert=True)
            return
        # Claim synchronously before the first await: double taps cannot send twice.
        context.user_data.pop("publish_pending", None)
        await query.answer()
        if action == "no":
            await edit_confirmation(query, "Cancelled. Nothing was posted to the channel.")
            return
        try:
            await check_channel(context.bot, pending["channel"]["id"], update.effective_user.id)
        except (ValueError, TelegramError):
            await edit_confirmation(
                query,
                "Channel permissions could not be verified. Nothing was posted. Check permissions and use /publish again.",
            )
            return
        post = pending["post"]
        sent = None
        try:
            sent = await context.bot.send_photo(
                pending["channel"]["id"],
                photo=post["file_id"],
                **photo_details(post["caption"]),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON, url=pending["url"])]]),
                write_timeout=60,
                read_timeout=60,
            )
            if utf16_len(post["caption"]) > 1024:
                await send_details(context.bot, pending["channel"]["id"], post["caption"])
        except TelegramError:
            await edit_confirmation(
                query,
                (
                    "The photo was posted, but sending its separate details failed. "
                    if sent
                    else "Telegram did not confirm delivery. The post may or may not have arrived. "
                )
                + "Check the channel before sending it again. Automatic retry is disabled to avoid duplicates.",
            )
            return
        await edit_confirmation(query, f"Posted to {pending['channel']['title']}. Message ID: {sent.message_id}")

    app.add_handler(CommandHandler(["setchannel", "channel"], setchannel))
    app.add_handler(CommandHandler("publish", publish))
    app.add_handler(CallbackQueryHandler(confirm, pattern=r"^pub:(yes|no):\d+:[0-9a-f]{16}$"))
