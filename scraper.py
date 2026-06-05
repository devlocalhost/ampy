#!/usr/bin/env python3
"""
Morphe APK Scraper - Run locally on your laptop
Usage:
    export GITHUB_TOKEN="your_token"
    python scraper.py

Downloads APKs into the current directory, uploads each one to the
GitHub release as soon as it's downloaded, then deletes the local file.
At the end it verifies every app is present in the release.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ── config ────────────────────────────────────────────────────────────────────
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPOSITORY", "myst-25/morphe-apk-scraper")
RELEASE_TAG  = "apks"
APPS_FILE    = Path(__file__).parent / "apps.json"
DOWNLOAD_DIR = Path(__file__).parent          # save right here, no sub-folder

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.6367.82 Mobile Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ── tiny helpers ──────────────────────────────────────────────────────────────

def banner(text):
    print(f"\n{'='*64}")
    print(f"  {text}")
    print(f"{'='*64}")

def log(msg):  print(f"  {msg}")
def ok(msg):   print(f"  \033[92m✔ {msg}\033[0m")
def err(msg):  print(f"  \033[91m✘ {msg}\033[0m")


def get_page(url, retries=3):
    for i in range(retries):
        try:
            r = SESSION.get(url, timeout=30, allow_redirects=True)
            log(f"GET {url[:90]}  →  HTTP {r.status_code}")
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 30))
                log(f"rate-limited, sleeping {wait}s")
                time.sleep(wait)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except Exception as e:
            log(f"attempt {i+1} failed: {e}")
            time.sleep(5 * (i + 1))
    return None


def soup(url):
    r = get_page(url)
    return BeautifulSoup(r.text, "html.parser") if r else None


def ver_slug(v):
    return re.sub(r"[^a-zA-Z0-9]+", "-", v).strip("-").lower()


def download_apk(url, dest, retries=3):
    """Stream-download url → dest. Returns True if valid APK saved."""
    for i in range(retries):
        try:
            with SESSION.get(url, stream=True, timeout=180,
                             allow_redirects=True) as r:
                ct   = r.headers.get("Content-Type", "")
                size = int(r.headers.get("Content-Length", 0))
                log(f"DL status={r.status_code}  ct={ct}  size={size//1024}KB")
                if "text/html" in ct or r.status_code >= 400:
                    log("blocked / not an APK, skipping")
                    return False
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(131072):
                        f.write(chunk)
            saved = dest.stat().st_size
            if saved < 500_000:
                log(f"file too small ({saved} B) – not a valid APK")
                dest.unlink(missing_ok=True)
                return False
            ok(f"saved {dest.name}  ({saved // 1024 // 1024} MB)")
            return True
        except Exception as e:
            log(f"download attempt {i+1} error: {e}")
            dest.unlink(missing_ok=True)
            time.sleep(8 * (i + 1))
    return False


# ── Source 1 : APKMirror ──────────────────────────────────────────────────────

def src_apkmirror(app):
    log("[APKMirror]")
    base    = app["apkmirror_url"].rstrip("/") + "/"
    version = app.get("version")
    package = app["package"]
    arch    = app.get("arch", "nodpi")

    # ── find release page
    s = soup(base)
    if not s:
        return None

    release_page = None
    if version:
        slug = ver_slug(version)
        for a in s.find_all("a", href=True):
            h = a["href"]
            if slug in h and "/apk/" in h and "download" not in h:
                release_page = "https://www.apkmirror.com" + h if h.startswith("/") else h
                break
        if not release_page:
            app_slug = base.rstrip("/").split("/")[-1]
            release_page = f"{base}{app_slug}-{slug}-release/"
    else:
        a = s.find("a", href=re.compile(r"-release/$"))
        if a:
            h = a["href"]
            release_page = "https://www.apkmirror.com" + h if h.startswith("/") else h

    if not release_page:
        log("no release page found")
        return None
    log(f"release_page={release_page}")

    # ── pick best variant
    s2 = soup(release_page)
    if not s2:
        return None
    candidates = []
    for a in s2.find_all("a", href=re.compile(r"/apk/.+/\d+/$")):
        pt = (a.find_parent() or a).get_text(" ", strip=True).upper()
        if "BUNDLE" in pt or "APKM" in pt:
            continue
        candidates.append((a["href"], pt.lower()))

    def score(item):
        h, t = item
        if arch and arch != "nodpi" and arch.lower() in t:
            return 0
        if "nodpi" in t or "universal" in t:
            return 1
        return 2

    if not candidates:
        log("no variant candidates")
        return None
    candidates.sort(key=score)
    vh = candidates[0][0]
    variant_page = "https://www.apkmirror.com" + vh if vh.startswith("/") else vh
    log(f"variant_page={variant_page}")

    # ── interstitial
    s3 = soup(variant_page)
    if not s3:
        return None
    btn = s3.find("a", href=re.compile(r"download/\?key="))
    if not btn:
        log("no download button on variant page")
        return None
    ih = btn["href"]
    interstitial = "https://www.apkmirror.com" + ih if ih.startswith("/") else ih
    log(f"interstitial={interstitial}")

    # ── CDN url
    s4 = soup(interstitial)
    if not s4:
        return None
    final = None
    for a in s4.find_all("a", href=True):
        if "cdn.apkmirror.com" in a["href"] or re.search(r"\.apk(\?|$)", a["href"]):
            final = a["href"]
            break
    if not final:
        log("no CDN url found")
        return None
    log(f"CDN={final[:80]}")

    dest = DOWNLOAD_DIR / f"{package}.apk"
    return dest if download_apk(final, dest) else None


# ── Source 2 : Uptodown ───────────────────────────────────────────────────────

def src_uptodown(app):
    log("[Uptodown]")
    base    = app.get("uptodown_dlurl", "").rstrip("/")
    version = app.get("version")
    package = app["package"]
    if not base:
        log("no uptodown_dlurl configured")
        return None

    versions_url = f"{base}/versions"
    s = soup(versions_url) or soup(base)
    if not s:
        return None

    dl_page = None
    if version:
        for a in s.find_all("a", href=True):
            parent_text = (a.find_parent() or a).get_text(" ", strip=True)
            if version in parent_text and re.search(r"post-download|/download", a["href"]):
                dl_page = a["href"]
                break
    if not dl_page:
        a = s.find("a", href=re.compile(r"post-download|/download"))
        if a:
            dl_page = a["href"]
    if not dl_page:
        log("no download page link found")
        return None
    if not dl_page.startswith("http"):
        dl_page = urljoin(base, dl_page)
    log(f"dl_page={dl_page}")

    s2 = soup(dl_page)
    final = None
    if s2:
        btn = (s2.find("a", id="detail-download-button") or
               s2.find("a", attrs={"data-url": True}) or
               s2.find("a", href=re.compile(r"\.apk")))
        if btn:
            final = btn.get("href") or btn.get("data-url", "")
        if not final:
            meta = s2.find("meta", attrs={"http-equiv": "refresh"})
            if meta:
                m = re.search(r"url=(.+)", meta.get("content", ""), re.I)
                if m:
                    final = m.group(1).strip()
    if not final:
        log("falling back to dl_page as direct download")
        final = dl_page
    if not final.startswith("http"):
        final = urljoin(base, final)
    log(f"final={final[:80]}")

    dest = DOWNLOAD_DIR / f"{package}.apk"
    return dest if download_apk(final, dest) else None


# ── Source 3 : APKCombo ───────────────────────────────────────────────────────

def src_apkcombo(app):
    log("[APKCombo]")
    package  = app["package"]
    version  = app.get("version")
    base_url = app.get("apkcombo_url", f"https://apkcombo.com/apk/{package}")

    url = f"{base_url}/{version}" if version else base_url
    log(f"url={url}")
    s = soup(url) or soup(base_url)
    if not s:
        return None

    final = None
    for a in s.find_all("a", href=True):
        if re.search(r"\.apk(\?|$)", a["href"]):
            final = a["href"]
            break
    if not final:
        for tag in s.find_all(attrs={"data-src": re.compile(r"\.apk")}):
            final = tag["data-src"]
            break
    if not final:
        btn = s.find("a", class_=re.compile(r"download", re.I))
        if btn:
            final = btn.get("href", "")
    if not final:
        log("no download link found")
        return None
    if not final.startswith("http"):
        final = "https://apkcombo.com" + final
    log(f"final={final[:80]}")

    dest = DOWNLOAD_DIR / f"{package}.apk"
    return dest if download_apk(final, dest) else None


# ── GitHub Release helpers ────────────────────────────────────────────────────

def gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_or_create_release():
    base = f"https://api.github.com/repos/{GITHUB_REPO}"
    r = requests.get(f"{base}/releases/tags/{RELEASE_TAG}", headers=gh_headers())
    if r.status_code == 200:
        d = r.json()
        return d["id"], d["upload_url"]
    log("Release not found, creating...")
    r = requests.post(f"{base}/releases", headers=gh_headers(), json={
        "tag_name": RELEASE_TAG,
        "name": "APK Mirror",
        "body": "Auto-scraped APKs for Morphe patching.",
        "prerelease": False,
    })
    r.raise_for_status()
    d = r.json()
    return d["id"], d["upload_url"]


def list_assets(release_id):
    r = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/{release_id}/assets",
        headers=gh_headers(),
    )
    r.raise_for_status()
    return {a["name"]: a["id"] for a in r.json()}


def delete_asset(asset_id):
    requests.delete(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/assets/{asset_id}",
        headers=gh_headers(),
    )


def upload_asset(upload_url, path):
    url = re.sub(r"\{.*?\}", "", upload_url)
    h = {**gh_headers(), "Content-Type": "application/vnd.android.package-archive"}
    log(f"uploading {path.name}  ({path.stat().st_size // 1024 // 1024} MB) ...")
    with open(path, "rb") as f:
        r = requests.post(url, headers=h, params={"name": path.name},
                          data=f, timeout=600)
    if r.status_code in (200, 201):
        dl = r.json().get("browser_download_url", "")
        ok(f"uploaded → {dl}")
        return dl
    err(f"upload failed {r.status_code}: {r.text[:200]}")
    return ""


# ── per-app orchestration ─────────────────────────────────────────────────────

def process_app(app, release_id, upload_url):
    name    = app["name"]
    package = app["package"]
    version = app.get("version") or "latest"
    banner(f"{name}  |  {package}  |  v{version}")

    # try sources in order
    apk_path = None
    for label, fn in [("APKMirror", src_apkmirror),
                      ("Uptodown",  src_uptodown),
                      ("APKCombo",  src_apkcombo)]:
        try:
            result = fn(app)
            if result and result.exists():
                ok(f"got APK via {label}")
                apk_path = result
                break
        except Exception as e:
            err(f"{label} exception: {e}")
        time.sleep(2)

    if not apk_path:
        err(f"ALL sources failed for {name}")
        return False

    # replace old asset in release if present
    existing = list_assets(release_id)
    if apk_path.name in existing:
        log(f"deleting old asset {apk_path.name}")
        delete_asset(existing[apk_path.name])

    dl_url = upload_asset(upload_url, apk_path)

    # delete local file immediately after upload
    apk_path.unlink(missing_ok=True)
    log(f"deleted local {apk_path.name}")

    return bool(dl_url)


# ── final verification ────────────────────────────────────────────────────────

def verify_all(apps, release_id):
    banner("VERIFICATION")
    assets   = list_assets(release_id)
    missing  = []
    present  = []
    for app in apps:
        fname = f"{app['package']}.apk"
        if fname in assets:
            ok(fname)
            present.append(fname)
        else:
            err(f"MISSING: {fname}")
            missing.append(app["name"])
    print()
    print(f"  Present : {len(present)}/{len(apps)}")
    if missing:
        print(f"  Missing : {', '.join(missing)}")
    return missing


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN environment variable not set.")
        print("Run:  export GITHUB_TOKEN=your_token")
        sys.exit(1)

    with open(APPS_FILE) as f:
        apps = json.load(f)
    print(f"[*] Loaded {len(apps)} apps from apps.json")

    release_id, upload_url = get_or_create_release()
    print(f"[*] Release id={release_id}")

    failed = []
    for app in apps:
        success = process_app(app, release_id, upload_url)
        if not success:
            failed.append(app["name"])
        time.sleep(3)

    missing = verify_all(apps, release_id)

    banner("SUMMARY")
    total   = len(apps)
    ok_cnt  = total - len(failed)
    print(f"  Scraped & uploaded : {ok_cnt}/{total}")
    if failed:
        print(f"  Failed             : {', '.join(failed)}")
    if missing:
        print(f"  Missing in release : {', '.join(missing)}")
        sys.exit(1)
    else:
        ok(f"All {total} APKs verified in GitHub release!")
        print(f"  Release: https://github.com/{GITHUB_REPO}/releases/tag/{RELEASE_TAG}")


if __name__ == "__main__":
    main()
