# AniPost

A Telegram bot for **SL Animebay and SL Mangabay**. Search an anime or manga, get a branded poster and **bold details**, replace its artwork, then preview and confirm a channel post with a download button.

- `/anime` and `/manga` search AniList independently, including exact IDs and AniList URLs.
- 1920 × 1080 posters, supplied brand logos, title fitting, and taller artwork with rounded corners and no letterbox borders.
- The default is the original **red-and-black design with diagonal stripes**. Choose any supported color name or **any 24-bit RGB color** with `/color #RRGGBB`.
- `/setimage` replaces artwork for either anime or manga. It also updates the blurred background.
- Synopsis excerpt **on the poster image only**; details captions contain no synopsis.
- Bold captions in bot replies, publication previews, and channel posts. Links and mentions stay clickable.
- `/publish` sends a preview first and requires confirmation before posting.
- **PM2 configuration included** for running the Python bot after SSH disconnects and across VPS restarts.

No Telegram API ID/API hash, userbot session, AniList key, or image-generation API is needed. You need a BotFather token and a server with outbound HTTPS access to Telegram and AniList.

## Requirements

An Ubuntu/Debian VPS with Python **3.10 or newer** and Node.js/npm for PM2. Python 3.12 or 3.13 is recommended. The automated checks cover Python 3.10, 3.12, and 3.13.

`requirements.txt` installs Python packages. **PM2 is a Node.js process manager**, installed separately with npm; it does not belong in Python's requirements file.

The instructions below assume you are using the VPS's `root` shell, with the project at `/root/anipost`. For another Linux account, use its home directory and `sudo` for package installation; the PM2 configuration resolves its own project paths automatically.

## Install from the downloaded ZIP (no GitHub needed)

The repository can be added later. The ZIP contains the complete bot and extracts
into a folder named `anipost`.

### Existing bot: move from systemd to PM2

Download `anipost-full-20261016.zip` to your phone. In **normal phone Termux**
(outside the VPS SSH session):

```bash
scp ~/storage/downloads/anipost-full-20261016.zip root@YOUR_VPS_IP:/root/
```

Replace `YOUR_VPS_IP` with your server address. A phone Downloads path will not
exist inside the VPS shell.

On the **VPS**, install the system tools and PM2 if needed:

```bash
apt update
apt install -y unzip python3 python3-venv python3-pip nodejs npm nano
npm install -g pm2
cd /root
unzip anipost-full-20261016.zip
cd /root/anipost
bash setup.sh --migrate /root/animebay-poster-bot
.venv/bin/python check_setup.py
```

Use a fresh `/root/anipost` directory for this first installation. If one already
exists, back it up before extracting over it. The setup script installs Python
dependencies in `.venv`, imports your personal settings, and checks imports/fonts.
It does **not** start/stop bots, install PM2, or modify the old installation.

The importer keeps your `.env`, saved channel, selected colors, logos and literal
caption footer. If your new `.env` already exists, it stops rather than replacing
it: either use the fresh folder or keep your existing configuration and run
`bash setup.sh` without `--migrate`. See the migration section below for details.

After the offline check passes, stop the old instance before testing the new one:

```bash
systemctl stop animebay-poster
.venv/bin/python bot.py
```

Try `/anime Frieren`, `/manga One Piece`, `/color orange`, and `/setimage` in
Telegram. **Ctrl+C** stops the foreground test. If it works:

```bash
pm2 start ecosystem.config.js --only anipost
pm2 status
pm2 logs anipost --lines 50
```

**Ctrl+C** exits the PM2 log viewer without stopping the bot. Once the new bot
works, keep the old service from restarting on reboot:

```bash
systemctl disable animebay-poster
pm2 startup
```

Run the exact startup command PM2 prints if it asks, then save the process list:

```bash
pm2 save
```

If your old bot uses a different process manager, stop that specific process
instead of the `systemctl` command. Do not run both copies with the same token.

### Fresh bot: no previous installation

Upload and extract the ZIP, then run:

```bash
cd /root/anipost
bash setup.sh
nano .env
.venv/bin/python check_setup.py
.venv/bin/python bot.py
```

Fill in `.env` using the configuration section below. An empty
`ALLOWED_USER_IDS=` is allowed temporarily while obtaining your ID with `/id`,
but the offline check will ask you to configure it before normal use. After
successful testing, stop the foreground bot and use the PM2/reboot steps above.

### Updating an installation made from a ZIP

Before replacing source files, keep a backup of the folder and your `.env`/`data/`.
A new full ZIP contains no personal `.env` or runtime `data/`. Preserve those
files when updating, install its requirements, then restart only this bot:

```bash
cd /root/anipost
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python check_setup.py
pm2 restart anipost
```

## Fresh installation from GitHub (after repository publication)

### 1. Install system tools

Run these commands **on the VPS**, after SSH login:

```bash
apt update
apt install -y git python3 python3-venv python3-pip nodejs npm nano
python3 --version
node --version
npm install -g pm2
pm2 --version
```

If Node.js is older than 18, update it using the [official Node.js installation instructions](https://nodejs.org/en/download) before installing PM2.

### 2. Clone and install the bot

This path becomes available after the public repository is created. Until then, use the ZIP instructions above.

```bash
cd /root
git clone https://github.com/nandeepaanuradha-svg/anipost.git
cd /root/anipost
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp -n .env.example .env
nano .env
```

Using `.venv/bin/python -m pip` keeps packages inside the project. It also avoids Debian/Ubuntu's `externally-managed-environment` error. Do not use `pip install dotenv`; the package in the requirements is `python-dotenv`.

### 3. Configure `.env`

Create a bot using Telegram's **@BotFather** and paste its token into your local `.env`:

```dotenv
BOT_TOKEN=PASTE_BOTFATHER_TOKEN_HERE
ALLOWED_USER_IDS=123456789
LANGUAGES=Not specified
SEND_PNG=true
```

| Setting | Meaning |
| --- | --- |
| `BOT_TOKEN` | The token issued by BotFather. Replace the placeholder. |
| `ALLOWED_USER_IDS` | Authorized numeric Telegram user IDs, separated by commas. |
| `LANGUAGES` | Your own audio/subtitle language label. AniList does not detect tracks in your files. |
| `SEND_PNG` | `true` sends the original PNG as a document as well as the normal photo. `false` sends only the photo. |

To find your ID, temporarily leave `ALLOWED_USER_IDS=` empty, start the bot in the next step, and send `/id` in Telegram. Stop it with **Ctrl+C**, put your ID in `.env`, and start again. Only `/id` works for unauthorized users.

In nano: **Ctrl+O**, **Enter** saves; **Ctrl+X** exits.

```bash
chmod 600 .env
```

Your token, saved channels, color choices, and backups are excluded by `.gitignore`. Never commit your real `.env`.

### 4. Test once in the foreground

```bash
cd /root/anipost
.venv/bin/python bot.py
```

In your bot chat:

```text
/anime Frieren
/manga One Piece
```

Select a result. Confirm the poster and bold details arrive. When finished, **press Ctrl+C in the VPS terminal**. The foreground bot must stop before starting PM2.

### 5. Start with PM2

```bash
cd /root/anipost
pm2 start ecosystem.config.js --only anipost
pm2 status
pm2 logs anipost --lines 50
```

**Ctrl+C while viewing `pm2 logs` closes the log viewer; it does not stop the bot.** PM2 runs the bot separately, so disconnecting SSH will not stop it.

The ecosystem file uses this project's virtualenv, runs one Python process, disables watch mode, and allows time for shutdown. **Keep `instances: 1`**: Telegram polling must have one active process per bot token.

### 6. Start automatically after a VPS reboot

Run these as the **same Linux user** that started the bot:

```bash
pm2 startup
```

PM2 prints a startup command suited to your operating system and account. **Copy and run that exact command if prompted.** Then:

```bash
pm2 save
```

`pm2 save` records the PM2 process list. Both the startup service and the saved list are needed for restart after reboot. `pm2 startup` uses a Linux startup system; Android Termux/proot is not the same as a VPS and generally needs its own boot mechanism.

## Existing Animebay installation: migrate safely

Use this section if the old bot is in `/root/animebay-poster-bot`. Keep that folder until you have verified the new bot.

1. Install system tools and extract the ZIP (or clone the repository once published). Install its Python requirements in `.venv`.
2. **Before creating `.env` in the new folder**, import your old token, saved channel, saved colors, logos, and literal caption footer:

   ```bash
   cd /root/anipost
   .venv/bin/python migrate.py /root/animebay-poster-bot
   ```

   The importer reads the old files without running the old code. It refuses to overwrite existing personal settings. It does not copy the old source or modify the old installation. Custom footer text is stored in `data/footers.json`.

3. Stop the old instance before testing the new one. If it runs under the service we used previously:

   ```bash
   systemctl stop animebay-poster
   ```

   If you started it in tmux or a foreground terminal instead, stop **that specific instance** with Ctrl+C. If another PM2 process already runs it, stop that named process. Do not stop unrelated bots or your whole PM2 daemon.

4. Run `.venv/bin/python bot.py`, check `/anime`, `/manga`, `/color`, and `/setimage`, then stop with Ctrl+C.
5. Start the new bot under PM2 using steps 5–6 above. Once it works, prevent the old systemd instance from returning after reboot:

   ```bash
   systemctl disable animebay-poster
   ```

6. Generate a **fresh poster** after the switch. Old in-memory poster selections and publishing confirmations cannot survive a process restart.

To roll back, stop `anipost` in PM2, then start your old instance. Never run both copies with the same token.

## Commands

| Command | What it does |
| --- | --- |
| `/anime Frieren` | Search anime and choose a result/season. |
| `/anime 154587` or `/post 154587` | Generate an anime poster using its AniList ID. |
| `/manga One Piece` | Search manga. |
| `/manga 30013` | Generate a manga poster using its AniList ID. |
| `/anime https://anilist.co/anime/154587` | Use an anime URL; manga URLs work with `/manga`. |
| `/setimage` | Ask for a replacement picture for your latest generated poster in this chat. |
| `/cancelimage` | Cancel a waiting image request. |
| `/color orange` | Use a named color for your next poster. |
| `/color light blue` | Spaced color names work too. |
| `/color #ff7a18` | Select an exact RGB color. All 16,777,216 RGB shades are supported. |
| `/colors` | List supported color names. |
| `/color default` | Restore the original red design. `/color reset` does the same. |
| `/languages Japanese \| English subtitles` | Change your details language label for this session. |
| `/languages reset` | Restore the label from `.env`. |
| `/setchannel @YourChannel` | Save your publishing destination after permission checks. |
| `/publish t.me/your_link` | Preview your latest poster with a download button, then confirm. |
| `/id` | Show your numeric Telegram user ID. |
| `/help` | Show help. |

Plain text titles default to anime search. `/colour`, `/colours`, and `/channel` are aliases.

### Choosing colors

Colors are **manual**, with no automatic artwork matching. Names are case insensitive. `/colors` lists the names supplied by Pillow; custom hex codes give access to every RGB shade. Both `#RGB` and `#RRGGBB` work.

The familiar shortcuts `red`, `green`, `blue`, `purple`, `teal`, and `gold` keep the shades used in the earlier bot. For an exact standard red/green/blue, use `#ff0000`, `#00ff00`, or `#0000ff`. Other names use standard CSS colors.

A color changes accent lines, genre borders, and diagonal stripes. Text remains light on a dark background. Logos retain their original colors. Very dark colors have a lighter genre outline to keep the label boundary visible.

The setting applies to the **next** `/anime`, `/manga`, or `/setimage` in that chat. Existing messages are not recolored. Colors persist in `data/poster-colors.json`; authorized users in the same group share the chat's color choice.

### Replacing artwork

First generate a poster, then use any of these:

- Send a picture with `/setimage` as its caption.
- Send `/setimage`, then upload a picture within 10 minutes.
- Reply to your uploaded picture with `/setimage`.

Still JPEG, PNG, and WebP images are accepted, up to 12 MiB and 24 megapixels. Sending the image as a document avoids Telegram photo compression. Animated files are rejected. Transparent artwork is flattened onto a dark background.

The bot creates a **new poster**, keeps the original details, and uses the replacement for the cover and blurred background. `/publish` then uses the new photo. A previous publishing confirmation is cleared when its artwork is replaced; prepare a new one.

The picture fills a 682 × 864 area and is cropped to fit without stretching. A slightly high crop helps retain faces. Generate the anime/manga again to restore source artwork. A fresh poster is needed after restarting the bot.

### Publishing to your channel

1. Add the bot to the destination channel as an administrator with **Post Messages** permission.
2. Ensure your own Telegram account is the channel owner or an administrator who can post.
3. In a private bot chat, send `/setchannel @YourChannel`. For a private channel, use `/setchannel -1001234567890`; an invite link cannot be used to select the channel.
4. Generate a poster and send `/publish t.me/your_download_link` or a full HTTP/HTTPS URL.
5. Check the preview, destination and link, then press **✅ Publish** or **Cancel**.

The channel post includes the photo, **bold details**, and the **🔥 Click Here To Download 🔥** URL button. The bot uses the link you supply; it does not find, create, or test download links. If details are longer than Telegram's photo-caption limit, they follow the photo as separate bold messages. The button stays attached to the photo.

Reply to a recent generated **photo** with `/publish LINK` to select it instead of your latest photo. The original PNG document is not a publishing target. The latest 20 photos per user are remembered during a session. The publishing destination persists in `data/channel.json` and is shared by this bot installation.

Each preview freezes its title, image, details, link and destination. Confirmations expire after 15 minutes or a restart. They can be used once, and posting permissions are checked again on confirmation. If Telegram does not confirm delivery, check the channel before retrying: the bot deliberately does not resend a possibly delivered channel photo.

## PM2 everyday commands

Run these as the same Linux user used for installation:

```bash
pm2 status                          # List managed processes
pm2 logs anipost --lines 100         # Recent logs, then follow live output
pm2 logs anipost --lines 100 --nostream  # Recent logs only
pm2 restart anipost                  # Reload code and .env from disk
pm2 stop anipost                     # Stop this bot
pm2 start ecosystem.config.js --only anipost  # Start from its config
pm2 delete anipost                   # Remove only this bot from PM2
pm2 save                            # Save the current list for reboot
```

`pm2 logs anipost` replaces the old `journalctl -u animebay-poster` log command **when you run AniPost using PM2**. `tmux attach` only applies to programs started inside that tmux session.

Do not use `pm2 delete all`, `pm2 kill`, or `pm2 flush` to manage this one bot; those commands affect other processes/logs too. PM2's default logs live under the Linux user's `~/.pm2/logs/`. Rotate or clear AniPost's logs as needed for long-running deployments.

## Updating from GitHub (after publication)

```bash
cd /root/anipost
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
pm2 restart anipost
```

Saved `.env` and `data/` files are untracked and survive a normal pull. If you edit tracked source files yourself, commit or back up those changes before pulling; do not overwrite them blindly. A change to `ecosystem.config.js` should be applied with `pm2 startOrRestart ecosystem.config.js --only anipost`, then `pm2 save`.

## Custom footer and logos

The bundled defaults use the supplied Animebay/Mangabay logos and decorative footer. Replace `assets/logo.jpg` or `assets/mangabay-logo.jpg` to change the matching brand logo.

For a footer override, create `data/footers.json` as valid JSON:

```json
{
  "ANIME": "Your anime footer\n@YourChannel",
  "MANGA": "Your manga footer\n@YourMangaChannel"
}
```

`\n` means a new line inside a JSON string. Keep a footer under 1,801 UTF-16 code units. The footer is plain text; bold formatting and clickable links are added by Telegram entities. Editing `.env` requires a restart. Color and footer JSON files are read when generating posts.

## Data and source limitations

Anime captions include title, genres, year, rating, language label, runtime, release status/dates, country, format/episodes, director, and studio. Manga captions replace anime-specific fields with chapters, volumes, format, author and artist.

AniList scores are converted from /100 to /10. Missing data is shown as unknown/TBA rather than invented. For currently releasing titles, episode/chapter/volume counts may be absent; these values are metadata, not a live episode counter. Staff lookup uses the first 25 relevant AniList staff records, so a missing role can appear as “Not listed.”

Synopsis text is a cleaned excerpt of up to 55 words on the image; it is not a newly written summary. English titles are preferred, then romaji. The bundled font is suited to Latin/romanized text; native-only CJK titles can require a different font.

Requests are paced and metadata is cached for 15 minutes. A source HTTP 403, outage or rate limit cannot be fixed by changing a poster color. This version uses the official AniList GraphQL endpoint; it does not bundle an unofficial fallback API. Entries marked adult by AniList are excluded; an Ecchi genre tag alone does not hide a normal title.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `No module named ...` | Run `.venv/bin/python -m pip install -r requirements.txt`; confirm PM2 uses `.venv/bin/python`. |
| `externally-managed-environment` | Install into the virtualenv using the exact command above. |
| `Conflict: another getUpdates request` | Stop the other copy using this bot token, including the old systemd/tmux instance. Keep one PM2 instance. |
| Unauthorized / invalid token | Correct the local `BOT_TOKEN` and restart PM2. |
| “This bot is private” | Use `/id`, put that number in `ALLOWED_USER_IDS`, then restart. |
| HTTP 403 from AniList | AniList denied this server access. Check the source later or use another authorized network; there is no built-in fallback. |
| AniList busy / rate limit | Wait for the displayed cooldown. Requests during a cooldown fail promptly instead of hanging the bot. |
| `/setimage` asks for a poster first | Generate a fresh poster after a restart and in the same chat. |
| The color appears unchanged | `/color` affects the next generated poster. Logos keep their own colors. |
| Missing title in results | Try the exact AniList ID and correct `/anime` or `/manga` command. |
| Cannot publish | Check both your own channel membership and the bot's Post Messages permission. |
| PM2 says `errored` | Read `pm2 logs anipost --lines 100 --nostream`; check the token, virtualenv, folder permissions and source access. |
| No logs / process not found | Use the same Linux user that started PM2; run `pm2 status`. |
| Settings JSON error | Back up and repair the named JSON file in `data/`. Do not delete your saved settings without a backup. |
| Poster arrived but PNG failed | The poster is still available for publishing; retry generation only if you need its original PNG. |

Error logs include exception type and code locations. HTTP debug logging is disabled so bot-token URLs are not printed by normal request logging. Check logs before retrying uncertain delivery.

## Development and verification

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m ruff check .
.venv/bin/python -m unittest discover -s tests -v
```

Tests use mocked Telegram/AniList calls and render real PNGs locally. They do not send messages to a real channel. See [TESTING.md](TESTING.md) for verification notes and [docs/REVIEW.md](docs/REVIEW.md) for the code review fixes.

Generate a local preview without a Telegram token (requires working AniList access):

```bash
.venv/bin/python preview.py 154587 --color '#ff7a18' --output /tmp/anime-preview.png
.venv/bin/python preview.py 30013 --type manga --color teal --output /tmp/manga-preview.png
```

Quote a hex color in a shell: an unquoted `#` starts a shell comment. In Telegram, simply send `/color #ff7a18`.

## Project files

| File | Purpose |
| --- | --- |
| `bot.py` | Commands, authorization, poster delivery and custom-image flow. |
| `anilist.py`, `manga_api.py` | Shared paced source requests and anime/manga interfaces. |
| `poster.py`, `manga_poster.py` | Shared graphic layout and type-specific details. |
| `manual_colors.py` | All named colors, custom hex shades and saved chat preferences. |
| `caption_style.py`, `telegram_output.py` | Bold entities, clickable links, message splitting and safe status edits. |
| `publishing.py` | Destination setup, preview, confirmation and channel delivery. |
| `storage.py` | Atomic local settings writes. |
| `migrate.py` | Import personal configuration from the old bot folder. |
| `setup.sh`, `check_setup.py` | Prepare the virtualenv/config and verify local settings without contacting external services. |
| `ecosystem.config.js` | PM2 configuration using the Python virtualenv. |
| `preview.py` | Standalone poster generation. |
| `.env.example` | Configuration template; never a real token. |
| `assets/` | Supplied brand logos and DejaVu fonts/license. |
| `tests/`, `.github/workflows/checks.yml` | Offline regression checks and GitHub Actions. |

## Documentation and attribution

- [PM2 ecosystem configuration](https://pm2.keymetrics.io/docs/usage/application-declaration/)
- [PM2 startup and reboot persistence](https://pm2.keymetrics.io/docs/usage/startup/)
- [AniList API](https://docs.anilist.co/)
- [AniList rate limits](https://docs.anilist.co/guide/rate-limiting)
- [python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/)
- [Pillow color formats](https://pillow.readthedocs.io/en/stable/reference/ImageColor.html)

Code is available under the [MIT license](LICENSE). Supplied logos retain their owners' rights. AniList artwork belongs to its respective rights holders. Font terms are included in `assets/FONT-LICENSE.txt`; the code license does not replace those terms.
