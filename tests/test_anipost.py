import asyncio
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from PIL import Image, ImageColor
from telegram.error import BadRequest, TimedOut
import bot
import manual_colors as colors
import manga_poster
import poster
import publishing
from anilist import AniList, SourceError
from caption_style import bold_entities
from manga_api import MangaList
from storage import write_json
from telegram_output import detail_chunks, units


def bitmap(color="#336699"):
    output = io.BytesIO()
    Image.new("RGB", (500, 800), color).save(output, "PNG")
    return output.getvalue()


def media(kind="ANIME", ident=1):
    return {
        "id": ident,
        "type": kind,
        "isAdult": False,
        "title": {"english": "A & B <Special>"},
        "genres": ["Adventure", "Ecchi"],
        "description": "SYNOPSIS ONLY ON IMAGE",
        "format": "MANGA" if kind == "MANGA" else "TV",
        "startDate": {"year": 2012},
        "staff": {"edges": [{"role": "Story & Art", "node": {"name": {"full": "Example Author"}}}]},
    }


class ColorAndCaptionTests(unittest.TestCase):
    def test_every_named_color_and_hex_shades(self):
        for name in ImageColor.colormap:
            self.assertEqual(len(ImageColor.getrgb(colors.palette_for(name)[0])), 3)
        self.assertEqual(colors.normalize_color("Light Blue"), "#add8e6")
        self.assertEqual(colors.normalize_color("#AbC"), "#aabbcc")
        self.assertEqual(colors.normalize_color("ff7a18"), "#ff7a18")
        self.assertEqual(colors.palette_for("default")[0], "#f22545")
        for value in ["transparent", "not-a-color", "#abcde", "rgba(0,0,0,0)", "#12345678"]:
            with self.assertRaises(ValueError):
                colors.normalize_color(value)

    def test_settings_persist_per_chat_and_corruption_is_preserved(self):
        with tempfile.TemporaryDirectory() as d, patch.object(colors, "SETTINGS", Path(d) / "colors.json"):
            self.assertEqual(colors.get_color(10), "default")
            colors.save_color(10, "#f80")
            self.assertEqual(colors.get_color(10), "#ff8800")
            self.assertEqual(colors.get_color(11), "default")
            colors.SETTINGS.write_text("bad")
            with self.assertRaises(ValueError):
                colors.save_color(10, "red")
            self.assertEqual(colors.SETTINGS.read_text(), "bad")

    def test_bold_emoji_links_and_long_chunks(self):
        text = "🏷 A & B <Title>\n@MovieClubFamily https://t.me/example t.me/+Example"
        entities = bold_entities(text)
        self.assertEqual(entities[0].length, units(text))
        self.assertEqual([e.type for e in entities], ["bold", "mention", "url", "url"])
        for entity in entities:
            self.assertTrue(
                text.encode("utf-16-le")[entity.offset * 2 : (entity.offset + entity.length) * 2].decode("utf-16-le")
            )
        self.assertEqual(bold_entities(None), [])
        text = "🌟 Title\n" * 1800
        chunks = list(detail_chunks(text))
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(units(c) <= 3800 for c in chunks))

    def test_metadata_and_custom_footer(self):
        anime, manga = poster.caption(media()), manga_poster.caption(media("MANGA"))
        self.assertNotIn("SYNOPSIS ONLY ON IMAGE", anime + manga)
        self.assertIn("Format : TV", anime)
        self.assertIn("Chapters :", manga)
        self.assertIn("Artist : Example Author", manga)
        self.assertNotIn("RunTime", manga)
        with tempfile.TemporaryDirectory() as d, patch("storage.DATA", Path(d)):
            write_json(Path(d) / "footers.json", {"ANIME": "MY CUSTOM FOOTER"})
            self.assertTrue(poster.caption(media()).endswith("MY CUSTOM FOOTER"))

    def test_synopsis_cleanup_and_title_fit(self):
        self.assertEqual(
            poster.clean_description("<p>A &amp; B<br>home.</p> ~!spoiler!~ (Source: Test)"), "A & B home."
        )
        face, lines, step = poster.fit_lines("LONGTITLE" * 90, 890, 294, 84, 34, True, 4)
        self.assertLessEqual(len(lines) * step, 294)
        self.assertTrue(all(face.getlength(line) <= 890 for line in lines))

    def test_filled_taller_rounded_art_and_color(self):
        m = media()
        m["_poster_color"] = "#ff7a18"
        for renderer in [poster.render, manga_poster.render]:
            with Image.open(io.BytesIO(renderer(m, bitmap()))) as image:
                self.assertEqual(image.size, (1920, 1080))
                self.assertEqual(image.getpixel((300, 161)), (255, 122, 24))
                self.assertEqual(image.getpixel((1450, 965)), (51, 102, 153))
                self.assertNotEqual(image.getpixel((1104, 108)), (51, 102, 153))
        for raw in [None, b"broken"]:
            self.assertTrue(poster.render(m, raw).startswith(b"\x89PNG"))

    def test_image_validation(self):
        self.assertTrue(bot.prepare_image(bitmap()).startswith(b"\xff\xd8"))
        for raw in [b"broken", b"0" * (bot.MAX_IMAGE_BYTES + 1)]:
            with self.assertRaises(ValueError):
                bot.prepare_image(raw)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_does_not_hide_ecchi_titles(self):
        async def response(request):
            self.assertEqual(json.loads(request.content)["variables"]["type"], "ANIME")
            return httpx.Response(200, json={"data": {"Page": {"media": [media(), dict(media(), isAdult=True)]}}})

        api = AniList(httpx.AsyncClient(transport=httpx.MockTransport(response)))
        try:
            self.assertEqual(len(await api.search("Sankarea")), 1)
        finally:
            await api.close()

    async def test_type_cache_and_no_mutable_cache_leak(self):
        calls = []

        async def response(request):
            v = json.loads(request.content)["variables"]
            calls.append(v)
            return httpx.Response(200, json={"data": {"Media": media(v["type"], v["id"])}})

        api = AniList(httpx.AsyncClient(transport=httpx.MockTransport(response)))
        try:
            result = await api.get(1)
            result["title"]["english"] = "changed"
            self.assertNotEqual((await api.get(1))["title"]["english"], "changed")
            api.next_request = 0
            self.assertEqual((await MangaList(api).get(1))["type"], "MANGA")
            self.assertEqual(len(calls), 2)
        finally:
            await api.close()

    async def test_rate_limit_fast_cooldown(self):
        calls = []

        async def response(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "30"})

        api = AniList(httpx.AsyncClient(transport=httpx.MockTransport(response)))
        try:
            for _ in range(2):
                with self.assertRaisesRegex(SourceError, "seconds"):
                    await api.search("test")
            self.assertEqual(len(calls), 1)
        finally:
            await api.close()

    async def test_source_failures(self):
        for status, data in [(403, {}), (200, {"errors": [{"message": "failure"}]}), (200, [])]:

            async def response(request):
                return httpx.Response(status, json=data)

            api = AniList(httpx.AsyncClient(transport=httpx.MockTransport(response)))
            try:
                with self.assertRaises(SourceError):
                    await api.search("example")
            finally:
                await api.close()

    async def test_artwork_host_and_byte_limits(self):
        calls = []

        async def response(request):
            calls.append(request)
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"x" * (12 * 1024 * 1024 + 1))

        api = AniList(httpx.AsyncClient(transport=httpx.MockTransport(response)))
        try:
            for url in [
                "http://anilist.co/a",
                "https://anilist.co.evil.invalid/a",
                "https://user:pass@anilist.co/a",
                "https://anilist.co:bad/a",
            ]:
                self.assertIsNone(await api.image(url))
            self.assertEqual(calls, [])
            self.assertIsNone(await api.image("https://s4.anilist.co/test.png"))
        finally:
            await api.close()


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        old = bot.ALLOWED
        bot.ALLOWED = {7}
        self.addCleanup(setattr, bot, "ALLOWED", old)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        p = patch.object(colors, "SETTINGS", Path(temp.name) / "colors.json")
        p.start()
        self.addCleanup(p.stop)
        self.sent = NS(chat_id=44, message_id=3, photo=[NS(file_id="new-photo")])
        self.status = NS(edit_text=AsyncMock())
        self.msg = NS(
            chat_id=44,
            text="/anime Example",
            caption=None,
            photo=[],
            document=None,
            reply_to_message=None,
            reply_text=AsyncMock(return_value=self.status),
            reply_photo=AsyncMock(return_value=self.sent),
            reply_document=AsyncMock(),
        )
        self.api = NS(
            get=AsyncMock(return_value=media()),
            search=AsyncMock(return_value=[media()]),
            image=AsyncMock(return_value=bitmap()),
        )
        self.manga_api = NS(
            get=AsyncMock(return_value=media("MANGA")),
            search=AsyncMock(return_value=[media("MANGA")]),
            image=AsyncMock(return_value=bitmap()),
        )
        self.ctx = NS(
            user_data={},
            args=["Example"],
            bot_data={"api": self.api, "manga_api": self.manga_api, "render_slots": asyncio.Semaphore(2)},
            bot=NS(username="examplebot"),
        )
        self.up = NS(effective_user=NS(id=7), effective_message=self.msg, callback_query=None)

    async def test_manga_search_callback_and_bold_caption(self):
        await bot.manga(self.up, self.ctx)
        data = self.msg.reply_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
        self.assertTrue(data.endswith(":MANGA"))
        self.up.callback_query = NS(data=data, message=self.msg, answer=AsyncMock())
        await bot.pick(self.up, self.ctx)
        kw = self.msg.reply_photo.call_args.kwargs
        self.assertIn("Chapters", kw["caption"])
        self.assertEqual(kw["caption_entities"][0].type, "bold")
        self.assertIn("/manga/1", kw["reply_markup"].inline_keyboard[0][0].url)
        self.api.get.assert_not_called()
        self.assertFalse(self.ctx.user_data["busy"])

    async def test_status_or_png_failure_keeps_delivered_poster(self):
        self.status.edit_text.side_effect = BadRequest("not editable")
        self.msg.reply_document.side_effect = TimedOut()
        self.assertTrue(await bot.show_post(self.msg, self.ctx.user_data, self.ctx, 1))
        self.assertEqual(self.ctx.user_data["last_poster"]["file_id"], "new-photo")
        self.assertEqual(self.msg.reply_photo.await_count, 1)

    async def test_uncertain_photo_is_not_retried_or_saved(self):
        self.msg.reply_photo.side_effect = TimedOut()
        self.assertFalse(await bot.show_post(self.msg, self.ctx.user_data, self.ctx, 1))
        self.assertNotIn("last_poster", self.ctx.user_data)
        self.assertEqual(self.msg.reply_photo.await_count, 1)

    async def test_custom_manga_image_preserves_caption_and_updates_publish(self):
        target = {"id": 1, "kind": "MANGA", "media": media("MANGA"), "caption": "CUSTOM FOOTER"}
        self.ctx.user_data.update(image_targets={44: target}, publish_pending={"nonce": "old"})
        self.msg.text = "/setimage"
        await bot.setimage(self.up, self.ctx)
        self.assertIn("image_pending", self.ctx.user_data)
        self.msg.text = None
        self.msg.photo = [
            NS(
                file_size=100,
                get_file=AsyncMock(
                    return_value=NS(file_size=100, download_as_bytearray=AsyncMock(return_value=bitmap()))
                ),
            )
        ]
        await bot.setimage(self.up, self.ctx)
        self.assertEqual(self.ctx.user_data["last_poster"]["caption"], "CUSTOM FOOTER")
        self.assertEqual(self.ctx.user_data["last_poster"]["file_id"], "new-photo")
        self.assertEqual(self.ctx.user_data["image_targets"][44]["kind"], "MANGA")
        self.assertNotIn("publish_pending", self.ctx.user_data)
        self.assertNotIn("image_pending", self.ctx.user_data)
        self.manga_api.get.assert_not_called()
        self.manga_api.image.assert_not_called()

    async def test_invalid_image_does_not_destroy_previous_poster(self):
        self.ctx.user_data.update(
            image_targets={44: {"id": 1, "media": media(), "caption": "old"}}, last_poster={"file_id": "old"}
        )
        self.msg.text = "/setimage"
        self.msg.photo = [
            NS(
                file_size=100,
                get_file=AsyncMock(
                    return_value=NS(file_size=100, download_as_bytearray=AsyncMock(return_value=b"broken"))
                ),
            )
        ]
        await bot.setimage(self.up, self.ctx)
        self.assertEqual(self.ctx.user_data["last_poster"]["file_id"], "old")
        self.msg.reply_photo.assert_not_called()
        self.assertFalse(self.ctx.user_data["busy"])

    async def test_unauthorized_and_other_bot_images_not_downloaded(self):
        self.up.effective_user.id = 8
        asset = NS(get_file=AsyncMock())
        self.msg.photo = [asset]
        await bot.setimage(self.up, self.ctx)
        asset.get_file.assert_not_called()
        self.up.effective_user.id = 7
        self.msg.photo = []
        self.msg.text = "/setimage@anotherbot"
        self.msg.reply_text.reset_mock()
        await bot.setimage(self.up, self.ctx)
        self.msg.reply_text.assert_not_called()

    async def test_color_permissions_and_invalid_input(self):
        handlers = []
        colors.register(NS(add_handler=handlers.append), bot.access)
        self.ctx.args = ["rebeccapurple"]
        await handlers[0].callback(self.up, self.ctx)
        self.assertEqual(colors.get_color(44), "#663399")
        self.ctx.args = ["not", "a", "color"]
        await handlers[0].callback(self.up, self.ctx)
        self.assertEqual(colors.get_color(44), "#663399")
        self.up.effective_user.id = 9
        self.ctx.args = ["red"]
        await handlers[0].callback(self.up, self.ctx)
        self.assertEqual(colors.get_color(44), "#663399")


class PublishingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        handlers = []
        publishing.register(NS(add_handler=handlers.append), AsyncMock(return_value=True))
        self.publish, self.confirm = handlers[1].callback, handlers[2].callback
        self.channel = {"id": -1001234567890, "title": "Animebay"}
        self.post = {"file_id": "abc", "caption": "🏷 Anime details", "title": "Example", "chat_id": 44, "message_id": 4}
        self.ctx = NS(
            user_data={"last_poster": self.post},
            args=["t.me/+Example"],
            bot=NS(send_photo=AsyncMock(return_value=NS(message_id=42)), send_message=AsyncMock()),
        )
        self.msg = NS(chat_id=44, reply_to_message=None, reply_photo=AsyncMock(), reply_text=AsyncMock())
        self.up = NS(effective_user=NS(id=7), effective_message=self.msg)
        for p in [
            patch.object(publishing, "load_channel", return_value=self.channel),
            patch.object(publishing, "check_channel", new=AsyncMock(return_value=self.channel)),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def callback(self, action="yes", uid=7):
        nonce = self.ctx.user_data["publish_pending"]["nonce"]
        q = NS(
            data=f"pub:{action}:7:{nonce}", message=NS(chat_id=44), answer=AsyncMock(), edit_message_text=AsyncMock()
        )
        return NS(effective_user=NS(id=uid), callback_query=q)

    async def test_preview_one_use_and_bold_publication(self):
        await self.publish(self.up, self.ctx)
        self.ctx.bot.send_photo.assert_not_called()
        self.assertEqual(self.msg.reply_photo.call_args.kwargs["caption_entities"][0].type, "bold")
        up = self.callback()
        await self.confirm(up, self.ctx)
        await self.confirm(up, self.ctx)
        self.assertEqual(self.ctx.bot.send_photo.await_count, 1)
        kw = self.ctx.bot.send_photo.call_args.kwargs
        self.assertEqual(kw["caption_entities"][0].length, units(self.post["caption"]))
        button = kw["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.url, "https://t.me/+Example")
        self.assertEqual(button.text, "🔥 Click Here To Download 🔥")

    async def test_cancel_wrong_user_expiry_and_revoked_permissions(self):
        await self.publish(self.up, self.ctx)
        await self.confirm(self.callback(uid=8), self.ctx)
        self.ctx.bot.send_photo.assert_not_called()
        await self.confirm(self.callback("no"), self.ctx)
        self.ctx.bot.send_photo.assert_not_called()
        await self.publish(self.up, self.ctx)
        self.ctx.user_data["publish_pending"]["expires"] = time.monotonic() - 1
        await self.confirm(self.callback(), self.ctx)
        self.ctx.bot.send_photo.assert_not_called()
        await self.publish(self.up, self.ctx)
        with patch.object(publishing, "check_channel", new=AsyncMock(side_effect=ValueError("revoked"))):
            await self.confirm(self.callback(), self.ctx)
        self.ctx.bot.send_photo.assert_not_called()

    async def test_long_details_remain_bold(self):
        self.post["caption"] = "🌟" * 2500
        await self.publish(self.up, self.ctx)
        await self.confirm(self.callback(), self.ctx)
        self.assertIsNone(self.ctx.bot.send_photo.call_args.kwargs["caption"])
        calls = self.ctx.bot.send_message.call_args_list
        self.assertEqual("".join(c.args[1] for c in calls), self.post["caption"])
        self.assertTrue(all(c.kwargs["entities"][0].type == "bold" for c in calls))

    async def test_frozen_post_and_failed_final_status(self):
        await self.publish(self.up, self.ctx)
        up = self.callback()
        up.callback_query.edit_message_text.side_effect = BadRequest("not editable")
        self.ctx.user_data["last_poster"] = {"file_id": "different"}
        await self.confirm(up, self.ctx)
        self.assertEqual(self.ctx.bot.send_photo.call_args.kwargs["photo"], "abc")
        self.assertNotIn("publish_pending", self.ctx.user_data)

    def test_links(self):
        for value in ["https://t.me/+Example", "t.me/example", "https://example.com/?a=b"]:
            self.assertTrue(publishing.valid_link(value))
        for value in [
            "javascript:alert(1)",
            "https://user:pass@example.com",
            "https://example.com/a b",
            "https://example.com:bad/",
        ]:
            self.assertFalse(publishing.valid_link(value))


class MigrationTests(unittest.TestCase):
    def test_imports_configuration_and_literal_footer_without_running_old_code(self):
        from migrate import migrate

        with tempfile.TemporaryDirectory() as d:
            old, new = Path(d) / "old", Path(d) / "new"
            old.mkdir()
            new.mkdir()
            (old / "bot.py").write_text('raise RuntimeError("must never execute")')
            (old / "poster.py").write_text('raise RuntimeError("must never execute")\nFOOTER="ORIGINAL FOOTER"')
            (old / ".env").write_text("BOT_TOKEN=EXAMPLE_PLACEHOLDER")
            copied = migrate(old, new)
            self.assertIn(".env", copied)
            self.assertEqual(json.loads((new / "data/footers.json").read_text())["ANIME"], "ORIGINAL FOOTER")
            self.assertEqual((new / ".env").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                migrate(old, new)


class SetupTests(unittest.TestCase):
    def test_offline_check_reports_placeholder_without_printing_token(self):
        import check_setup

        with (
            patch.object(check_setup, "load_dotenv"),
            patch.dict("os.environ", {"BOT_TOKEN": "PASTE_BOTFATHER_TOKEN_HERE", "ALLOWED_USER_IDS": ""}, clear=True),
        ):
            errors = check_setup.check()
        self.assertTrue(any("BOT_TOKEN" in value for value in errors))
        self.assertTrue(any("ALLOWED_USER_IDS" in value for value in errors))
        self.assertFalse(any("PASTE_BOTFATHER" in value for value in errors))

    def test_offline_check_accepts_configured_values(self):
        import check_setup

        with (
            patch.object(check_setup, "load_dotenv"),
            patch.dict(
                "os.environ",
                {"BOT_TOKEN": "12345:TEST_PLACEHOLDER", "ALLOWED_USER_IDS": "7", "SEND_PNG": "true"},
                clear=True,
            ),
        ):
            self.assertEqual(check_setup.check(), [])


if __name__ == "__main__":
    unittest.main()
