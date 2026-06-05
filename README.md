# ampy 📦

A fast, smart APK downloader that scrapes the latest versions of your favourite Android apps directly from **APKMirror** and **UptoDown** — with automatic fallback when one source is blocked.

---

## What is this?

`ampy` is a command-line tool that lets you search for any Android app and download the latest APK automatically. It picks the best available variant (universal architecture, nodpi) so the APK works on every phone.

It is also fully compatible with **GitHub Actions**, meaning you can set it up once and trigger a download + release of all your apps from the cloud at any time — no manual work required.

---

## How the Scraper Works

When you run `ampy` and search for an app, it follows this flow:

```
User searches "Instagram"
        │
        ▼
 Try APKMirror first
        │
    ┌───┴───────────────────┐
    │  200 OK?              │  403 / Blocked?
    ▼                       ▼
Download from          Auto-switch to
APKMirror ✓            UptoDown ✓
```

### APKMirror
The primary source. It has the most accurate and up-to-date APK releases. The scraper:
1. Searches for the app by name and version
2. Parses the search results page to find matching releases
3. Scores every available variant by architecture and DPI to pick the best one:
   - Prefers **universal** architecture (runs on any processor — ARM, ARM64, x86)
   - Prefers **nodpi** DPI (graphics scale perfectly on every screen size)
   - Prefers bare `.apk` over `.apkm` / `.apks` bundles
4. Navigates through three pages to get the final direct download URL
5. Downloads and saves the file

### UptoDown (Automatic Fallback)
Some apps — like Instagram, Facebook, and WhatsApp — are aggressively protected by Cloudflare's **Turnstile** bot challenge on APKMirror. No browser automation can solve this challenge without human interaction.

For these apps, the scraper **automatically falls back** to UptoDown, which serves the same apps without any bot protection. The flow is:
1. APKMirror returns `403 Forbidden`
2. Scraper detects the block immediately
3. Switches to UptoDown, looks up the correct app slug
4. Downloads the latest APK directly from UptoDown's CDN

This all happens invisibly — you just get your APK.

---

## File Naming

All downloaded APKs follow the standard naming format:

```
com.google.android.youtube-21.21.80-all.apk
com.instagram.android-433.0.0.4.68-all.apk
com.twitter.android-11.91.0-release.0-all.apk
```

Format: `[package.name]-[version]-all.apk`

This format is required by automated patching pipelines (like ReVanced) that look for APKs by package name.

---

## Installation

```bash
git clone https://github.com/myst-25/ampy
cd ampy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

### Interactive Mode

Run the script and you will get a menu:

```bash
python apkmcli
```

```
╔══════════════════════════════╗
║        APK Downloader        ║
╚══════════════════════════════╝

Quick pick (from apps.json):
  [1] YouTube 21.21.80
  [2] YouTube Music 9.21.51
  [3] X 11.91.0-release.0
  [4] Instagram latest
  [5] Download ALL above
  [0] Custom search

 →
```

- Pick a number to download that specific app
- Pick **[5]** to download every app in `apps.json` at once
- Pick **[0]** to search for any app by name

### Custom Search

Choose `[0]` and type any app name:

```
App name to search:
 → Spotify

Version (leave blank for latest):
 → 
```

The scraper will search APKMirror first. If it gets blocked, it automatically switches to UptoDown. If an old APK for that app already exists in the `builds/` folder, it will ask you before deleting it:

```
Found existing APK(s):
  com.spotify.music-8.9.94-all.apk (68.2 MB)
Delete old APK(s) before downloading? (y/n):
 →
```

### Batch / Automated Mode

```bash
python apkmcli --download-all
```

Reads `apps.json` and downloads every app silently — no prompts, no questions. Old APKs are automatically replaced. This is the mode used by GitHub Actions.

---

## apps.json

This file defines the apps downloaded in batch mode. Add or remove apps here:

```json
{
    "YouTube": "21.21.80",
    "YouTube Music": "9.21.51",
    "X": "11.91.0-release.0",
    "Instagram": "latest"
}
```

- The **key** is the app name as it appears on APKMirror
- The **value** is the version string, or `"latest"` for UptoDown-sourced apps

Downloaded APKs are saved to the `builds/` folder.

---

## GitHub Actions Setup

The GitHub Actions workflow lets you trigger downloads from anywhere, at any time, without your laptop needing to be manually set up each time — except for one thing: **the proxy**.

### Why a Proxy?

APKMirror blocks all requests coming from cloud server IP addresses (AWS, Azure, GitHub Actions, etc.). To bypass this, the GitHub Actions runner tunnels all its traffic through your personal laptop using **Tailscale**, which gives the traffic your home IP address.

UptoDown does **not** require a proxy — its direct downloads bypass Cloudflare entirely and are always fetched directly from the GitHub runner.

### Setting Up Tailscale

Tailscale creates a private, secure VPN between your laptop and the GitHub Actions runner.

**Step 1 — Install Tailscale on your laptop:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

**Step 2 — Get your laptop's Tailscale IP:**
```bash
tailscale ip -4
# Example output: 100.90.77.61
```

**Step 3 — Generate a reusable Auth Key:**
1. Go to [tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys)
2. Click **Generate auth key**
3. Check both **Reusable** and **Ephemeral**
4. Copy the key (starts with `tskey-auth-...`)

**Step 4 — Add the key to GitHub Secrets:**
1. Go to your repo on GitHub → **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `TAILSCALE_AUTHKEY`
4. Value: paste your `tskey-auth-...` key

### Starting the Local Proxy

Before triggering the GitHub Action, start the proxy on your laptop:

```bash
~/.local/bin/proxy --hostname 0.0.0.0 --port 8899
```

> **Important:** Use `--hostname 0.0.0.0` — this tells the proxy to listen on the Tailscale network interface, not just localhost. Without this, the GitHub Actions runner cannot connect.

The workflow hardcodes your Tailscale IP (`100.90.77.61`) as the proxy address. If your Tailscale IP ever changes, update the `HTTP_PROXY` and `HTTPS_PROXY` lines in `.github/workflows/download_apks.yml`.

### Triggering the Workflow

1. Make sure your proxy is running (`~/.local/bin/proxy --hostname 0.0.0.0 --port 8899`)
2. Go to your repo on GitHub → **Actions** → **APK Downloader**
3. Click **Run workflow** → **Run workflow**

The runner will:
1. Connect to your laptop via Tailscale VPN
2. Download YouTube, YouTube Music, X via APKMirror (through your home IP proxy)
3. Download Instagram via UptoDown (direct — no proxy needed)
4. Create a new GitHub Release with all APKs attached

### Releases

Every workflow run creates a new GitHub Release tagged with the current date and time:

```
release-2026.06.05-1530
APK Builds - 2026.06.05-1530
```

All APKs are attached to the release as assets, ready to download.

---

## How the Auto-Fallback Works (Technical)

The `apkmirror.py` scraper's `search()` method returns:
- A **list of results** → app found, proceed with download
- An **empty list** → no results found, try UptoDown
- `None` → blocked by Cloudflare (403), immediately switch to UptoDown

The `apkmcli` script checks for `None` before anything else and reroutes the download to UptoDown transparently.

UptoDown's `get_app_slug()` method tries three strategies to find the correct app page:
1. Check the built-in known-apps dictionary (YouTube, Instagram, X, etc.)
2. Search UptoDown's search endpoint to find the slug dynamically
3. Guess the slug by converting the app name to lowercase with hyphens

---

## Supported Apps (Known Package Names)

| App | Package Name | Source |
|-----|-------------|--------|
| YouTube | `com.google.android.youtube` | APKMirror |
| YouTube Music | `com.google.android.apps.youtube.music` | APKMirror |
| X (Twitter) | `com.twitter.android` | APKMirror |
| Instagram | `com.instagram.android` | UptoDown (auto-fallback) |
| TikTok | `com.zhiliaoapp.musically` | UptoDown (auto-fallback) |
| WhatsApp | `com.whatsapp` | UptoDown (auto-fallback) |
| Snapchat | `com.snapchat.android` | UptoDown (auto-fallback) |
| Facebook | `com.facebook.katana` | UptoDown (auto-fallback) |
| Telegram | `org.telegram.messenger` | APKMirror |
| Spotify | `com.spotify.music` | APKMirror |

Any app not in this list will still download correctly — it just won't have a known package name, so the filename will use the scraped app name instead.

---

## Project Structure

```
ampy/
├── apkmcli              # Main CLI script — entry point
├── apkmirror.py         # APKMirror scraper (primary source)
├── uptodown.py          # UptoDown scraper (automatic fallback)
├── apkm_converter.py    # Extracts base APK from .apkm / .apks bundles
├── apps.json            # Apps to download in batch mode
├── requirements.txt     # Python dependencies
├── builds/              # Downloaded APKs saved here
└── .github/
    └── workflows/
        └── download_apks.yml  # GitHub Actions workflow
```

---

## License

MIT
