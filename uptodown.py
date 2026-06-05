"""
UptoDown APK scraper — works for ALL apps including Instagram
that are blocked on APKMirror by Cloudflare Turnstile.

URL pattern: https://[app-slug].en.uptodown.com/android/download
Download URL: https://dw.uptodown.com/dwn/[token]
"""

import time
import re
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import cloudscraper


# Map known app names to their UptoDown slugs
APP_SLUGS = {
    "YouTube": "youtube",
    "YouTube Music": "youtube-music",
    "X": "twitter",
    "Instagram": "instagram",
    "TikTok": "tik-tok",
    "WhatsApp": "whatsapp",
    "Snapchat": "snapchat",
    "Facebook": "facebook",
    "Telegram": "telegram",
    "Spotify": "spotify",
}


class UptoDown:
    def __init__(self, timeout=2):
        self.timeout = timeout
        self.base_url = "https://en.uptodown.com"
        self.dw_base = "https://dw.uptodown.com/dwn"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://en.uptodown.com/",
        }
        self.scraper = cloudscraper.create_scraper()

    def _get(self, url):
        time.sleep(self.timeout)
        return self.scraper.get(url, headers=self.headers, timeout=15)

    def get_app_slug(self, app_name):
        """Get the UptoDown slug: check known list first, then search UptoDown."""
        slug = APP_SLUGS.get(app_name)
        if slug:
            return slug

        # Try searching UptoDown for the app
        slug = self._search_slug(app_name)
        if slug:
            return slug

        # Last resort: guess the slug from the name
        return app_name.lower().replace(" ", "-")

    def _search_slug(self, app_name):
        """Search UptoDown to find the correct app slug."""
        try:
            query = quote_plus(app_name)
            # UptoDown search API
            url = f"https://en.uptodown.com/android/search/{query}"
            r = self.scraper.get(url, headers=self.headers, timeout=10)
            if r.status_code != 200:
                # Try alternative search format
                url = f"https://en.uptodown.com/android/q/{query}"
                r = self.scraper.get(url, headers=self.headers, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                # Find first result app link
                result = soup.find("a", {"class": "item"})
                if not result:
                    result = soup.find("div", {"class": "item"})
                    if result:
                        result = result.find("a")
                if result and result.get("href"):
                    href = result["href"]
                    # Extract slug from URL like https://instagram.en.uptodown.com/android
                    import re
                    m = re.search(r"https?://([^.]+)\.en\.uptodown\.com", href)
                    if m:
                        return m.group(1)
        except Exception as e:
            print(f"[uptodown] Search error: {e}")
        return None

    def get_download_info(self, app_name, target_version=None):
        """Get the specified version (or latest) and direct download URL for an app."""
        slug = self.get_app_slug(app_name)
        app_url = f"https://{slug}.en.uptodown.com/android"
        
        target_version = target_version.strip() if target_version else None
        if target_version and target_version.lower() != "latest":
            # Search for specific version
            versions_url = f"{app_url}/versions"
            print(f"[uptodown] Fetching versions from {versions_url}")
            r = self._get(versions_url)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                versions_list = soup.find("div", {"id": "versions-items-list"})
                if versions_list:
                    for item in versions_list.find_all("div", recursive=False):
                        v_span = item.find("span", {"class": "version"})
                        if v_span and target_version in v_span.text.strip():
                            v_id = item.get("data-version-id")
                            if v_id:
                                download_page_url = f"{app_url}/download/{v_id}"
                                return self._parse_download_page(app_name, app_url, download_page_url)
            print(f"[uptodown] Target version '{target_version}' not found. Falling back to latest.")

        # Default to latest
        download_page_url = f"{app_url}/download"
        return self._parse_download_page(app_name, app_url, download_page_url)

    def _parse_download_page(self, app_name, app_url, download_page_url):
        print(f"[uptodown] Fetching {download_page_url}")
        r = self._get(download_page_url)

        if r.status_code != 200:
            print(f"[uptodown] Failed: status {r.status_code}")
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Get the download token from the button
        btn = soup.find("button", {"id": "detail-download-button"})
        if not btn:
            print("[uptodown] Could not find download button")
            return None

        token = btn.get("data-url")
        if not token:
            print("[uptodown] No download token found")
            return None

        # Get version info
        version = None
        version_el = soup.find("span", {"itemprop": "version"})
        if not version_el:
            version_el = soup.find("div", {"class": "version"})
        if version_el:
            version = version_el.text.strip()

        direct_url = f"{self.dw_base}/{token}"

        return {
            "app_name": app_name,
            "version": version or "unknown",
            "download_url": direct_url,
            "app_page": app_url,
        }

    def download(self, app_name, version=None, output_dir="builds", package_name=None):
        """Download the latest APK for an app."""
        import os

        info = self.get_download_info(app_name, target_version=version)
        if not info:
            print(f"[uptodown] Could not get download info for {app_name}")
            return None

        version = info["version"]
        print(f"[uptodown] Downloading {app_name} {version} from {info['download_url']}")

        # Build filename using package name if provided
        os.makedirs(output_dir, exist_ok=True)
        if package_name:
            filename = os.path.join(output_dir, f"{package_name}-{version}-all.apk")
        else:
            clean = app_name.replace(" ", "_")
            filename = os.path.join(output_dir, f"{clean}-{version}-all.apk")

        # Delete old versions
        import glob
        if package_name:
            old_files = glob.glob(os.path.join(output_dir, f"{package_name}-*-all.*"))
        else:
            old_files = glob.glob(os.path.join(output_dir, f"{app_name.replace(' ', '_')}-*-all.*"))
        for f in old_files:
            try:
                os.remove(f)
                print(f"[uptodown] Removed old: {f}")
            except Exception:
                pass

        r = self.scraper.get(info["download_url"], headers=self.headers, stream=True, timeout=60)
        if r.status_code != 200:
            print(f"[uptodown] Download failed: status {r.status_code}")
            return None

        # Try to get filename from the URL (e.g. instagram-433-0.0.4-68.apk)
        final_url = r.url
        url_filename = final_url.split("/")[-1]
        if url_filename.endswith(".apk") and package_name:
            filename = os.path.join(output_dir, f"{package_name}-{version}-all.apk")

        print(f"[uptodown] Saving to {filename}...")
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"[uptodown] Done: {filename}")
        return filename
