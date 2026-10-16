# Code review — consolidated AniPost

This release replaces the sequence of ZIP patches with one complete project. Review covered source requests, rendering, settings, Telegram delivery, channel publishing, installation, and PM2 configuration.

## Fixes included

1. **Normal titles hidden by a genre filter.** Removed the blanket Ecchi exclusion. Entries marked adult by AniList are still excluded. Anime and manga use the same rule.
2. **False error after successful delivery.** Failure to edit a status message or send the optional PNG no longer turns an already delivered poster into a failed request. It is saved for publishing immediately after the photo succeeds.
3. **Plain details in publication paths.** Bold entities are applied to generated photo captions, long separate details, publication previews, and channel posts. UTF-16 lengths handle emoji correctly. Link/mention entities preserve clickability.
4. **Duplicated or inconsistent renderer patches.** Anime and manga share one renderer, retaining separate logos and metadata captions. The default is the original red theme; artwork is taller and still fills a rounded box.
5. **Limited color choices.** All Pillow CSS color names and every #RRGGBB shade are accepted. Color selection is explicit, saved per chat, and never inferred from artwork. Dark colors retain a visible genre boundary.
6. **Rate-limit requests could wait too long.** Long source cooldowns now return promptly with a retry time; normal requests share a paced client and 15-minute cache.
7. **Mutable cache values.** Cached media is copied on read, so a per-chat color cannot contaminate another user's poster. Anime/manga cache entries include the media type.
8. **Concurrent result taps.** The busy flag is claimed before answering the callback, preventing simultaneous generation from two rapid selections by the same user.
9. **Image captions targeting another bot.** Both text and image `/setimage@botname` commands check the intended bot. Invalid images preserve the previous publishing target.
10. **Bare t.me links.** `/publish t.me/...` is normalized to HTTPS and still passes URL validation. Download links are supplied by the user, never fetched by the bot.
11. **Final publication status edits.** Once a channel send succeeds, a failure to edit the confirmation message cannot trigger a second send. Confirmation is still one-use; uncertain network delivery is never automatically retried.
12. **Fragile settings writes.** JSON settings are written to temporary files and atomically replaced. Corrupt settings are reported rather than silently overwritten.
13. **Public-repository hygiene.** No live token, personal settings, runtime logs, backups, or virtualenv is included. Only `.env.example` is tracked. Migration reads literal footer text without executing old source.
14. **Process-manager confusion.** PM2 uses the virtualenv interpreter, one fork-mode instance, no file watcher, and delayed restarts. The README distinguishes foreground runs, PM2 log viewing, old systemd migration, and reboot persistence.

## Scope of verification

Offline regression tests run real image rendering and mock external API/message calls. Linting checks Python source. PM2 configuration is checked separately. This review does not prove that AniList accepts a particular VPS IP, that a real Telegram token is valid, or that a user/channel has posting permissions; those checks happen on deployment.

15. **Repository dependency in installation.** Added a direct ZIP path, a setup helper that never starts/stops services, and an offline configuration checker. GitHub publication is optional and deferred.
