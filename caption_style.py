"""Telegram bold entities with emoji-safe offsets and clickable links."""

import re
from telegram import MessageEntity


def _units(s):
    return len(s.encode("utf-16-le")) // 2


def bold_entities(text):
    if not text or not text.strip():
        return []
    result = [MessageEntity("bold", 0, _units(text.rstrip()))]
    for m in re.finditer(r"https?://[^\s<>]+|(?<![\w/])t\.me/[^\s<>]+|(?<!\w)@[A-Za-z0-9_]{5,32}\b", text):
        result.append(
            MessageEntity("mention" if m[0].startswith("@") else "url", _units(text[: m.start()]), _units(m[0]))
        )
    return result
