"""Deterministic 1920x1080 Animebay design; no image-generation API required."""

import html
import io
import re
from pathlib import Path
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
RED = "#f22545"
WHITE = "#f7f1e9"
MUTED = "#b8b9c1"
W, H = 1920, 1080
FOOTER = (
    "┏━━━━•❅•°•❈•°•❅•━━━━┓\n✰ 👑•°𝚂ʟ ᐃ𝚗ɪᴍ𝚎ʙ𝚊𝚢°•👑 ✰\n┗━━━━•❅•°•❈•°•❅•━━━━┛\n🎭Proudly Presented By🎭\n@MovieClubFamily"
)


@lru_cache(maxsize=96)
def font(size, bold=False):
    return ImageFont.truetype(str(ASSETS / ("bold.ttf" if bold else "regular.ttf")), size)


def title(media):
    t = media.get("title") or {}
    return t.get("english") or t.get("romaji") or t.get("native") or "Untitled anime"


def clean_description(value):
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", value or "", flags=re.S | re.I)
    value = re.sub(r"~!.*?!~", "", value, flags=re.S)
    value = re.sub(r"<br\s*/?>|</p>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.split(r"\(Source:|\[Source:|\n\s*(?:Source:|Notes?:)", value, maxsplit=1, flags=re.I)[0]
    return " ".join(value.split())


def shorten(text, count):
    return text if len(text) <= count else text[: count - 1].rstrip() + "…"


def wrap(text, face, width):
    lines, line = [], ""
    # Break long unspaced words too, so metadata cannot spill into artwork.
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if face.getlength(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
            line = ""
        for char in word:
            if line and face.getlength(line + char) > width:
                lines.append(line)
                line = ""
            line += char
    if line:
        lines.append(line)
    return lines


def fit_lines(text, width, height, largest, smallest, bold=False, max_lines=20):
    for size in range(largest, smallest - 1, -1):
        f = font(size, bold)
        lines = wrap(text, f, width)
        step = int(size * 1.22)
        if len(lines) <= max_lines and len(lines) * step <= height:
            return f, lines, step
    f = font(smallest, bold)
    step = int(smallest * 1.22)
    limit = max(1, min(max_lines, height // step))
    lines = wrap(text, f, width)
    shown = lines[:limit]
    if len(lines) > limit:
        last = shown[-1]
        while last and f.getlength(last + "…") > width:
            last = last[:-1]
        shown[-1] = last.rstrip() + "…"
    return f, shown, step


def decode(raw):
    if not raw:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width * im.height > 24_000_000:
                return None
            return ImageOps.exif_transpose(im).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def render(media, cover_bytes=None, banner_bytes=None, *, kind="ANIME"):
    from manual_colors import palette_for

    accent, stripe, border = palette_for(media.get("_poster_color", "default"))
    brand = "MANGABAY" if kind == "MANGA" else "ANIMEBAY"
    logo = "mangabay-logo.jpg" if kind == "MANGA" else "logo.jpg"
    spotlight = "M A N G A   S P O T L I G H T" if kind == "MANGA" else "A N I M E   S P O T L I G H T"
    cover, banner = decode(cover_bytes), decode(banner_bytes)
    canvas = Image.new("RGB", (W, H), "#0b0c13")
    if banner or cover:
        backdrop = ImageOps.fit(banner or cover, (W, H), method=Image.Resampling.LANCZOS)
        backdrop = backdrop.filter(ImageFilter.GaussianBlur(5))
        canvas = Image.blend(backdrop, canvas, 0.57)
    # Smooth readable dark panel blending across the artwork.
    gradient = Image.new("L", (W, 1))
    gradient.putdata([int(246 * max(0, min(1, (1380 - x) / 560))) for x in range(W)])
    canvas.paste(Image.new("RGB", (W, H), "#0b0c13"), (0, 0), gradient.resize((W, H)))
    d = ImageDraw.Draw(canvas)
    d.polygon([(0, 0), (580, 0), (537, 8), (0, 8)], fill=accent)
    d.polygon([(1810, 0), (1858, 0), (1360, 1080), (1312, 1080)], fill=accent)
    d.polygon([(1890, 0), (1900, 0), (1402, 1080), (1392, 1080)], fill=stripe)
    # Original supplied logo on a light badge; crop only the known surrounding whitespace.
    with Image.open(ASSETS / logo) as src:
        if src.width == src.height:
            src = src.crop(
                (int(src.width * 0.105), int(src.height * 0.18), int(src.width * 0.845), int(src.height * 0.845))
            )
        badge = ImageOps.contain(src.convert("RGB"), (158, 142), Image.Resampling.LANCZOS)
    d.rounded_rectangle((68, 44, 248, 206), radius=12, fill="#ededed")
    canvas.paste(badge, (158 - badge.width // 2, 125 - badge.height // 2))
    d.text((278, 72), "SL " + brand, font=font(32, True), fill=WHITE)
    d.text((280, 121), spotlight, font=font(18), fill=MUTED)
    d.line((280, 161, 830, 161), fill=accent, width=3)
    f, lines, step = fit_lines(title(media).upper(), 890, 294, 84, 34, True, 4)
    y = 258
    for line in lines:
        d.text((68, y), line, font=f, fill=WHITE, stroke_width=0)
        y += step
    d.line((70, 576, 177, 576), fill=accent, width=7)
    # Genre chips fit on one row.
    x = 68
    for genre in (media.get("genres") or ["ANIME"])[:3]:
        label = genre.upper()
        tw = int(font(20, True).getlength(label)) + 32
        if x + tw > 962:
            break
        d.rounded_rectangle((x, 604, x + tw, 646), radius=5, outline=border, width=2)
        d.text((x + 16, 613), label, font=font(20, True), fill=WHITE)
        x += tw + 14
    summary = clean_description(media.get("description")) or "A synopsis is not available from AniList yet."
    # Short excerpt on the image only; keep text readable and don't copy an entire long description.
    words = summary.split()
    if len(words) > 55:
        summary = " ".join(words[:55]).rstrip(".,;:") + "…"
    f, lines, step = fit_lines(summary, 880, 205, 30, 27, max_lines=6)
    for i, line in enumerate(lines):
        d.text((68, 686 + i * step), line, font=f, fill="#d6d5dc")
    if cover or banner:
        # Fill the complete artwork area; crop overflow without stretching.
        # A slightly high crop keeps faces near the top of portrait covers.
        size = (682, 864)
        fitted = ImageOps.fit(cover or banner, size, Image.Resampling.LANCZOS, centering=(0.5, 0.3))
        scale = 4
        mask = Image.new("L", (size[0] * scale, size[1] * scale), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, size[0] * scale - 1, size[1] * scale - 1), radius=32 * scale, fill=255
        )
        mask = mask.resize(size, Image.Resampling.LANCZOS)
        canvas.paste(fitted, (1104, 108), mask)
    else:
        d.text((1150, 485), "ARTWORK UNAVAILABLE", font=font(27, True), fill=MUTED)
    year = (media.get("startDate") or {}).get("year") or media.get("seasonYear") or "TBA"
    fmt = (media.get("format") or "ANIME").replace("_", " ")
    score = f"{media['averageScore'] / 10:g}/10" if media.get("averageScore") else "N/A"
    d.text((70, 944), f"{year}    /    {fmt}    /    ANILIST {score}", font=font(22, True), fill=WHITE)
    d.line((68, 1000, 1852, 1000), fill="#393440", width=1)
    d.text((68, 1024), "S L   " + " ".join(brand), font=font(20, True), fill=WHITE)
    d.text((1460, 1026), "DATA & ART: ANILIST", font=font(17), fill=MUTED)
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


def date_text(value):
    value = value or {}
    if not value.get("year"):
        return "TBA"
    return "-".join(str(value[k]).zfill(2 if k != "year" else 4) for k in ("year", "month", "day") if value.get(k))


def caption(media, languages="Not specified"):
    studios = ", ".join(n["name"] for n in (media.get("studios") or {}).get("nodes", [])) or "Not listed"
    directors = (
        ", ".join(
            dict.fromkeys(
                e["node"]["name"]["full"]
                for e in (media.get("staff") or {}).get("edges", [])
                if e.get("role", "").lower() in {"director", "chief director"}
            )
        )
        or "Not listed"
    )
    country = media.get("countryOfOrigin") or "Not listed"
    country = {"JP": "Japan", "CN": "China", "KR": "South Korea", "TW": "Taiwan"}.get(country, country)
    start = date_text(media.get("startDate"))
    end = date_text(media.get("endDate"))
    status = (media.get("status") or "Not listed").replace("_", " ").title()
    score = f"{media['averageScore'] / 10:g}/10 (AniList)" if media.get("averageScore") else "Not rated"
    runtime = f"{media['duration']} min" if media.get("duration") else "Not listed"
    if media.get("format") != "MOVIE" and media.get("duration"):
        runtime += " / episode"
    release = f"{status} | {start}" + (f" → {end}" if end != "TBA" and end != start else "")
    rows = [
        ("🏷 Title", shorten(title(media), 160)),
        ("🎭 Genres", shorten(", ".join(media.get("genres") or []) or "Not listed", 100)),
        ("📆 Years", str((media.get("startDate") or {}).get("year") or media.get("seasonYear") or "TBA")),
        ("🌟 Rating", score),
        ("☀️ Languages", shorten(languages, 70)),
        ("📀 RunTime", runtime),
        ("📆 Release Info", release),
        ("🎛 Countries", country),
        (
            "📺 Format",
            (media.get("format") or "Not listed").replace("_", " ")
            + (
                f" • {media['episodes']} episodes"
                if media.get("episodes")
                else (" • Episodes TBA" if media.get("format") != "MOVIE" else "")
            ),
        ),
        ("🎬 Director", shorten(directors, 100)),
        ("🏢 Studio", shorten(studios, 100)),
    ]
    return "\n".join(f"{k} : {v}" for k, v in rows) + "\n\n" + get_footer("ANIME")


def utf16_len(text):
    return len(text.encode("utf-16-le")) // 2


def get_footer(kind="ANIME"):
    from storage import DATA, read_json

    values = read_json(DATA / "footers.json", {})
    if not isinstance(values, dict):
        raise ValueError("Invalid footers.json; expected an object with ANIME and MANGA keys.")
    default = FOOTER if kind == "ANIME" else FOOTER.replace("ᐃ𝚗ɪᴍ𝚎ʙ𝚊𝚢", "ᗰᴀɴɢᴀʙᴀʏ")
    value = values.get(kind, default)
    if not isinstance(value, str) or utf16_len(value) > 1800:
        raise ValueError("Caption footer must be text under 1801 UTF-16 units.")
    return value
