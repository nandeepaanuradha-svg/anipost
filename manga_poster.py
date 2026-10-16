"""Mangabay details with the shared poster layout and supplied manga logo."""

from poster import date_text, get_footer, shorten, title
from poster import render as _render


def render(media, cover_bytes=None, banner_bytes=None):
    return _render(media, cover_bytes, banner_bytes, kind="MANGA")


def caption(media, languages="Not specified"):
    edges = (media.get("staff") or {}).get("edges") or []

    def people(roles):
        names = [e["node"]["name"]["full"] for e in edges if e.get("role", "").lower() in roles]
        return shorten(", ".join(dict.fromkeys(names)) or "Not listed", 140)

    author = people({"story", "story & art", "original story"})
    artist = people({"art", "story & art"})
    country = media.get("countryOfOrigin") or "Not listed"
    country = {"JP": "Japan", "CN": "China", "KR": "South Korea", "TW": "Taiwan"}.get(country, country)
    start, end = date_text(media.get("startDate")), date_text(media.get("endDate"))
    status = (media.get("status") or "Not listed").replace("_", " ").title()
    release = f"{status} | {start}" + (f" → {end}" if end != "TBA" and end != start else "")
    score = f"{media['averageScore'] / 10:g}/10 (AniList)" if media.get("averageScore") else "Not rated"
    rows = [
        ("🏷 Title", shorten(title(media), 160)),
        ("🎭 Genres", shorten(", ".join(media.get("genres") or []) or "Not listed", 100)),
        ("📆 Years", str((media.get("startDate") or {}).get("year") or "TBA")),
        ("🌟 Rating", score),
        ("☀️ Languages", shorten(languages, 70)),
        ("📚 Chapters", str(media.get("chapters") or "Not listed")),
        ("📚 Volumes", str(media.get("volumes") or "Not listed")),
        ("📆 Release Info", release),
        ("🎛 Countries", country),
        ("📖 Format", (media.get("format") or "MANGA").replace("_", " ").title()),
        ("✍️ Author", author),
        ("🎨 Artist", artist),
    ]
    return "\n".join(f"{k} : {v}" for k, v in rows) + "\n\n" + get_footer("MANGA")
