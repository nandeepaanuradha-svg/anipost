"""Shared, paced AniList client for anime and manga metadata and artwork."""

import asyncio
import copy
import math
import time
from urllib.parse import urlsplit
import httpx

FIELDS = """id type isAdult title { english romaji native } description(asHtml: false)
format status episodes duration chapters volumes averageScore genres countryOfOrigin seasonYear
startDate { year month day } endDate { year month day }
coverImage { extraLarge large } bannerImage siteUrl
studios(isMain: true) { nodes { name } }
staff(perPage: 25, sort: RELEVANCE) { edges { role node { name { full } } } }"""
SEARCH = """query ($search: String!, $type: MediaType!) { Page(page: 1, perPage: 6) {
media(search: $search, type: $type, isAdult: false, sort: SEARCH_MATCH) {
id type isAdult title { english romaji native } format startDate { year } genres
} } }"""
DETAIL = "query ($id: Int!, $type: MediaType!) { Media(id: $id, type: $type, isAdult: false) {" + FIELDS + "} }"


class SourceError(Exception):
    """Safe source error that may be shown in Telegram."""


class AniList:
    def __init__(self, client=None):
        self.http = client or httpx.AsyncClient(
            timeout=25, follow_redirects=False, headers={"User-Agent": "AniPost/1.0 (Animebay and Mangabay poster bot)"}
        )
        self.lock = asyncio.Lock()
        self.next_request = 0.0
        self.cache = {}

    async def close(self):
        await self.http.aclose()

    async def query(self, query, variables):
        async with self.lock:
            delay = max(0, self.next_request - time.monotonic())
            if delay > 3:
                raise SourceError(f"AniList is busy. Try again in {math.ceil(delay)} seconds.")
            for attempt in range(3):
                await asyncio.sleep(max(0, self.next_request - time.monotonic()))
                self.next_request = time.monotonic() + 2.2
                try:
                    response = await self.http.post(
                        "https://graphql.anilist.co", json={"query": query, "variables": variables}
                    )
                except httpx.RequestError:
                    if attempt == 2:
                        raise SourceError("AniList could not be reached. Please try again shortly.") from None
                    await asyncio.sleep(2**attempt)
                    continue
                if response.status_code == 429:
                    try:
                        delay = float(response.headers.get("Retry-After", "60"))
                        if not math.isfinite(delay):
                            delay = 60
                    except ValueError:
                        delay = 60
                    delay = max(1, delay)
                    self.next_request = time.monotonic() + delay
                    raise SourceError(f"AniList is busy. Please try again in {math.ceil(delay)} seconds.")
                if response.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                if response.status_code == 403:
                    raise SourceError(
                        "AniList denied this server access (HTTP 403). Try again later; color or title changes cannot fix source access."
                    )
                if response.status_code == 404:
                    raise SourceError("That title was not found or is not available in this bot.")
                if response.status_code != 200:
                    raise SourceError(f"AniList returned HTTP {response.status_code}. Please try again later.")
                try:
                    body = response.json()
                except ValueError:
                    raise SourceError("AniList returned an unreadable response.") from None
                if not isinstance(body, dict) or body.get("errors") or not isinstance(body.get("data"), dict):
                    raise SourceError("AniList could not complete this search. Please try another title.")
                return body["data"]
        raise SourceError("AniList is temporarily unavailable.")

    @staticmethod
    def suitable(media):
        # A genre tag alone (for example Ecchi) must not hide a normal title.
        return isinstance(media, dict) and not media.get("isAdult", True)

    @staticmethod
    def check_type(media_type):
        if media_type not in {"ANIME", "MANGA"}:
            raise ValueError("Unsupported media type")

    async def search(self, text, media_type="ANIME"):
        self.check_type(media_type)
        data = await self.query(SEARCH, {"search": text[:160], "type": media_type})
        page = data.get("Page") or {}
        return [m for m in page.get("media") or [] if self.suitable(m) and m.get("type") == media_type]

    async def get(self, ident, media_type="ANIME"):
        self.check_type(media_type)
        now = time.monotonic()
        key = (media_type, int(ident))
        item = self.cache.get(key)
        if item and item[0] > now:
            return copy.deepcopy(item[1])
        media = (await self.query(DETAIL, {"id": int(ident), "type": media_type})).get("Media")
        if not self.suitable(media) or media.get("type") != media_type:
            raise SourceError(
                "This title is not available for that command. Check its AniList ID and use /anime or /manga."
            )
        if len(self.cache) >= 128:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = (now + 900, copy.deepcopy(media))
        return media

    async def image(self, url):
        if not url or not isinstance(url, str):
            return None
        try:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.port not in (None, 443)
                or not (parsed.hostname == "anilist.co" or parsed.hostname.endswith(".anilist.co"))
            ):
                return None
            async with self.http.stream("GET", url) as response:
                if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
                    return None
                output = bytearray()
                async for chunk in response.aiter_bytes():
                    output.extend(chunk)
                    if len(output) > 12 * 1024 * 1024:
                        return None
                return bytes(output)
        except (httpx.RequestError, ValueError):
            return None
