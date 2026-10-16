"""Named and exact RGB colors, chosen explicitly and saved per chat."""

import re
from PIL import ImageColor
from storage import DATA, read_json, write_json

SETTINGS = DATA / "poster-colors.json"
# Keep the original familiar red default and previous shortcut shades.
PRESETS = {
    "red": "#f22545",
    "green": "#36c983",
    "blue": "#4285f4",
    "purple": "#9a55d5",
    "teal": "#45cfc1",
    "gold": "#d4ba86",
}


def normalize_color(value):
    if not isinstance(value, str):
        raise ValueError("Color must be a name or #RRGGBB text.")
    text = re.sub(r"[\s_-]+", "", value.strip().lower())
    if text in {"default", "reset"}:
        return "default"
    if text in PRESETS:
        return text
    if re.fullmatch(r"[a-f0-9]{3}|[a-f0-9]{6}", text):
        text = "#" + text
    if not (text in ImageColor.colormap or re.fullmatch(r"#[a-f0-9]{3}(?:[a-f0-9]{3})?", text)):
        raise ValueError("Use a color name or #RRGGBB. Examples: /color orange, /color light blue, /color #ff7a18.")
    rgb = ImageColor.getrgb(text)
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def load():
    value = read_json(SETTINGS, {})
    if not isinstance(value, dict):
        raise ValueError("Invalid poster-colors.json; expected a JSON object.")
    return value


def get_color(chat_id):
    return normalize_color(load().get(str(chat_id), "default"))


def save_color(chat_id, color):
    value = load()
    value[str(chat_id)] = normalize_color(color)
    write_json(SETTINGS, value)


def palette_for(color):
    color = normalize_color(color)
    accent = PRESETS.get(color, "#f22545" if color == "default" else color)
    rgb = ImageColor.getrgb(accent)
    stripe = "#773243" if color in {"default", "red"} else tuple(round(v * 0.42) for v in rgb)
    # Very dark colors still have visible genre borders on a dark background.
    border = tuple(max(85, v) for v in rgb) if max(rgb) < 85 else rgb
    return accent, stripe, border


def register(app, access):
    from telegram.ext import CommandHandler

    async def color(update, context):
        if not await access(update):
            return
        message = update.effective_message
        try:
            if not context.args:
                current = get_color(message.chat_id)
                await message.reply_text(
                    f"Current color: {current}\n"
                    "Choose any named color or exact #RRGGBB shade.\n"
                    "/color blue\n/color light blue\n/color #ff7a18\n"
                    "/color default — original red theme\n/colors — list names\n"
                    "Applies to the next /anime, /manga or /setimage in this chat and survives restarts."
                )
                return
            if context.user_data.get("busy"):
                await message.reply_text("Wait for your current poster to finish, then change its color.")
                return
            chosen = normalize_color(" ".join(context.args))
            save_color(message.chat_id, chosen)
            await message.reply_text(f"Color saved: {chosen}. Generate a new poster or use /setimage.")
        except (OSError, ValueError) as exc:
            await message.reply_text(
                str(exc) if isinstance(exc, ValueError) else "The color could not be saved. Check the VPS logs."
            )

    async def colors(update, context):
        if not await access(update):
            return
        names = ", ".join(sorted(ImageColor.colormap))
        await update.effective_message.reply_text(
            "Available named colors:\n" + names + "\n\n"
            "Spaces are accepted: /color light blue.\n"
            "Every RGB shade is available with /color #RRGGBB.\n"
            "Shortcuts red/green/blue/purple/teal/gold use the original bot shades; "
            "use hex for an exact RGB value. /color default restores red."
        )

    app.add_handler(CommandHandler(["color", "colour"], color))
    app.add_handler(CommandHandler(["colors", "colours"], colors))
