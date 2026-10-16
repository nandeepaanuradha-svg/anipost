"""Manga interface sharing anime requests, rate limits and cache."""


class MangaList:
    def __init__(self, api):
        self.api = api

    async def search(self, text):
        return await self.api.search(text, media_type="MANGA")

    async def get(self, ident):
        return await self.api.get(ident, media_type="MANGA")

    async def image(self, url):
        return await self.api.image(url)
