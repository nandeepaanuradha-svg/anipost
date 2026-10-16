"""Bold details and best-effort status updates, without duplicate photo retries."""

import logging
from telegram.error import TelegramError
from caption_style import bold_entities

LOG = logging.getLogger("anipost")


def units(text):
    return len(text.encode("utf-16-le")) // 2


def detail_chunks(text, limit=3800):
    current, length = "", 0
    for char in text:
        size = units(char)
        if length + size > limit:
            yield current
            current, length = "", 0
        current += char
        length += size
    if current:
        yield current


async def reply_details(message, text):
    for chunk in detail_chunks(text):
        await message.reply_text(chunk, entities=bold_entities(chunk), parse_mode=None)


async def send_details(bot, chat_id, text):
    for chunk in detail_chunks(text):
        await bot.send_message(chat_id, chunk, entities=bold_entities(chunk), parse_mode=None)


def photo_details(text):
    shown = text if units(text) <= 1024 else None
    return {"caption": shown, "caption_entities": bold_entities(shown), "parse_mode": None}


async def edit_status(status, text):
    try:
        await status.edit_text(text)
    except TelegramError as exc:
        # A completed poster is still successful if editing its status fails.
        LOG.info("Status edit skipped (%s)", type(exc).__name__)
