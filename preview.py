"""Generate an anime or manga poster without Telegram credentials."""

import argparse
import asyncio
from pathlib import Path
from anilist import AniList, SourceError
from manual_colors import normalize_color
from poster import render


async def make(args):
    api = AniList()
    try:
        media = await api.get(args.id, args.type.upper())
        media["_poster_color"] = normalize_color(args.color)
        info = media.get("coverImage") or {}
        cover, banner = await asyncio.gather(
            api.image(info.get("extraLarge") or info.get("large")), api.image(media.get("bannerImage"))
        )
        output = await asyncio.to_thread(render, media, cover, banner, kind=args.type.upper())
        args.output.write_bytes(output)
        print(f"Saved {args.output}")
    finally:
        await api.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("id", type=int, help="AniList media ID")
    parser.add_argument("--type", choices=["anime", "manga"], default="anime")
    parser.add_argument("--color", default="default", help="Color name or quoted #RRGGBB")
    parser.add_argument("--output", type=Path, default=Path("/tmp/anipost-preview.png"))
    args = parser.parse_args()
    try:
        asyncio.run(make(args))
    except (SourceError, ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
