from urllib.parse import quote_plus
import time

from bs4 import BeautifulSoup

import cloudscraper

BASE_URL = "https://www.apkmirror.com"
BASE_SEARCH = f"{BASE_URL}/?post_type=app_release&searchtype=apk&s="
USER_AGENT_STRING = "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0"  # "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT_STRING}

scraper = cloudscraper.create_scraper()


def search(query):
    print("[search] Sleeping...")

    time.sleep(5)

    search_url = BASE_SEARCH + quote_plus(query)
    resp = scraper.get(search_url, headers=HEADERS)

    print(f"[search] Status: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    apps = []
    appRow = soup.find_all("div", {"class": "appRow"})

    for app in appRow:
        try:
            app_dict = {
                "name": app.find("h5", {"class": "appRowTitle"}).text.strip(),
                "link": BASE_URL + app.find("a", {"class": "downloadLink"})["href"],
                "image": BASE_URL
                + app.find("img", {"class": "ellipsisText"})["src"]
                .replace("h=32", "h=96")
                .replace("w=32", "w=96"),
            }

            apps.append(app_dict)

        except AttributeError:
            pass

    return apps[:5]


def get_app_details():
    print("[get_app_details] Sleeping...")

    time.sleep(5)

    resp = scraper.get(search("discord")[0]["link"], headers=HEADERS)

    print(f"[get_app_details] Status: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")

    data = soup.find_all("div", {"class": ["table-row", "headerFont"]})[1]

    architecture = data.find_all(
        "div",
        {
            "class": [
                "table-cell",
                "rowheight",
                "addseparator",
                "expand",
                "pad",
                "dowrap",
            ]
        },
    )[1].text.strip()
    android_version = data.find_all(
        "div",
        {
            "class": [
                "table-cell",
                "rowheight",
                "addseparator",
                "expand",
                "pad",
                "dowrap",
            ]
        },
    )[2].text.strip()
    dpi = data.find_all(
        "div",
        {
            "class": [
                "table-cell",
                "rowheight",
                "addseparator",
                "expand",
                "pad",
                "dowrap",
            ]
        },
    )[3].text.strip()
    download_link = BASE_URL + data.find_all("a", {"class": "accent_color"})[0]["href"]

    return architecture, android_version, dpi, download_link


def get_download_link():
    print("[get_download_link] Sleeping...")

    time.sleep(5)

    resp = scraper.get(get_app_details()[3], headers=HEADERS)

    print(f"[get_download_link] Status: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    return BASE_URL + str(soup.find_all("a", {"class": "downloadButton"})[0]["href"])


def get_direct_download_link():
    print("[get_direct_download_link] Sleeping...")

    time.sleep(5)

    resp = scraper.get(get_download_link(), headers=HEADERS)

    print(f"[get_direct_download_link] Status: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")

    data = soup.find(
        "a",
        {
            "rel": "nofollow",
            "data-google-vignette": "false",
            "href": lambda href: href
            and "/wp-content/themes/APKMirror/download.php" in href,
        },
    )["href"]

    return BASE_URL + str(data)


def main():
    # print(search("discord")[0]["link"])
    # print(get_app_details())
    # print(get_download_link())
    print(get_direct_download_link())


if __name__ == "__main__":
    main()
