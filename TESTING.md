# Verification

Reviewed and checked on 16 October 2026.

## Passed locally

- `python -m ruff check .`: no findings.
- `python -m unittest discover -s tests -q`: **27 tests passed**.
- Real PNG rendering for both brand variants, including missing artwork, long titles, taller filled artwork, rounded corners, selected color, and custom footer preservation.
- All installed Pillow color names plus custom/short hex values; settings persistence and corrupt-settings protection.
- Emoji-safe bold entity lengths, clickable links/mentions, and splitting long details.
- Mocked AniList anime/manga routing, adult flag handling, Ecchi search, separate cache keys, mutable-cache isolation, 429 cooldown behavior, clear source failures, image host validation and byte limits.
- Mocked Telegram image replacement, unauthorized requests, rejected files, false failure after successful delivery, and uncertain delivery without a duplicate send.
- Mocked publishing preview/confirmation, one-use confirmation, cancel/expiry/ownership/permissions, frozen drafts, bold separate details and bare t.me normalization.
- Migration imports a token placeholder and literal footer **without executing old source**; existing personal settings are protected.
- Node loaded `ecosystem.config.js` and checked one fork-mode instance, project cwd, virtualenv interpreter and disabled watch mode.
- The real Python polling application started and shut down cleanly against a local mocked Telegram request implementation.
- Public-source scan found no live token/key patterns. `.env`, runtime data, backups and local environments are ignored.

- `bash setup.sh` completed locally: virtualenv package installation, configuration-template creation, Python imports and bundled fonts passed.
- `check_setup.py` tests cover placeholder detection, configured values, and keeping credentials out of output.
- README includes direct ZIP installation and old-folder migration without requiring a GitHub repository.

## Environment limitation

A full PM2-daemon smoke test was attempted, but this execution environment refused PM2's Unix IPC socket connections (`EPERM`). It was not a bot exception. The ecosystem configuration was validated, and the Python application lifecycle was tested separately. PM2 must still be checked on the target VPS using the README's `pm2 status` and `pm2 logs anipost` steps.

## External checks still required on deployment

No live Telegram account/channel was messaged. A VPS must verify its own BotFather token, authorized user IDs, AniList access, and channel admin permissions. GitHub Actions runs the offline tests on Python 3.10, 3.12 and 3.13 when the workflow is enabled; local results do not imply that those remote jobs have run yet.
