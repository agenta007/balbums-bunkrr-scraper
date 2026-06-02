#!/usr/bin/env python3
"""Scrape Bunkr album links from balbums.st and download small videos.
Uses caching.
Every found album is cached with all file links.
--update updates cache, else program uses cached sqlite links (and only redownloads files)
--skip-existing
--overwrite
"""
from __future__ import annotations
import argparse
import datetime
import html
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse, urlencode
from playwright.sync_api import sync_playwright
import bs4
import requests
from vars import *
from helpers import is_valid_video
from tqdm import tqdm

class _Session:
    """Playwright browser session shared across all fetch/download calls."""

    def __init__(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.firefox.launch(headless=True)
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        self._context.add_cookies(COOKIE_LIST)
        self._page = self._context.new_page()

    def fetch_html(self, url: str, timeout: int = 20) -> str:
        self._page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        return self._page.content()

    def resolve_final_download_url(self, file_url: str) -> Optional[str]:
        html = fetch_html(file_url)
        soup = bs4.BeautifulSoup(html, "html.parser")

        # try jsCDN variable first (direct CDN url in page JS)
        match = re.search(r'var jsCDN\s*=\s*"([^"]+)"', html)
        if match:
            cdn_url = match.group(1).replace("\\/", "/")
            # sign the URL
            signed = self._sign_cdn_url(cdn_url)
            if signed:
                return signed

        # fallback: grab href from download button (get.bunkrr.su link, no signing needed)
        btn = soup.find("a", class_=lambda c: c and "btn-main" in c)
        if btn and btn.get("href"):
            href = btn["href"].replace("\\/", "/")
            if href.startswith("http"):
                return href
            return urljoin(file_url, href)

        return None

    def _sign_cdn_url(self, cdn_url: str) -> Optional[str]:
        try:
            from urllib.parse import urlparse, urlencode, urlunparse
            path = urlparse(cdn_url).path
            sign_url = f"https://glb-apisign.cdn.cr/sign?path={requests.utils.quote(path)}"
            r = requests.get(sign_url, timeout=10)
            r.raise_for_status()
            data = r.json()
            token = data.get("token")
            ex = data.get("ex")
            if not token or not ex:
                return None
            return f"{cdn_url}?token={token}&ex={ex}"
        except Exception as exc:
            print(f"[warn] failed to sign CDN url {cdn_url}: {exc}")
            return None

    def resolve_final_download_url_playwright(self, file_url: str, timeout: int = 30) -> Optional[str]:
        # hop 1: click download-btn and catch the download event
        self._page.goto(file_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        print(self._page.content())
        try:
            with self._page.expect_download(timeout=timeout * 1000) as download_info:
                self._page.click("a.btn.btn-main.btn-lg.rounded-full.ic-download-01")
            intermediate = download_info.value.url
            download_info.value.cancel()
        except Exception:
            # fallback: build intermediate URL from data-id
            soup = bs4.BeautifulSoup(self._page.content(), "html.parser")
            container = soup.find(id="download-btn")
            if not container:
                return None
            data_id = container.get("data-id")
            if not data_id:
                return None
            intermediate = f"https://get.bunkrr.su/d/{data_id}"

        if not intermediate:
            return None

        # hop 2: land on intermediate page, intercept the CDN request
        cdn_url: list[str] = []

        def intercept(route):
            url = route.request.url
            ext = Path(urlparse(url).path).suffix.lower()
            if ext in VIDEO_EXTENSIONS or ext in IMAGE_EXTENSIONS:
                cdn_url.append(url)
                route.abort()
            else:
                route.continue_()

        self._page.route("**/*", intercept)
        try:
            self._page.goto(intermediate, wait_until="domcontentloaded", timeout=timeout * 1000)
            link = self._page.query_selector("a[href]")
            if link:
                with self._page.expect_download(timeout=timeout * 1000) as dl:
                    link.click()
                cdn_url.append(dl.value.url)
                dl.value.cancel()
            else:
                self._page.wait_for_timeout(5000)
        except Exception:
            pass
        finally:
            self._page.unroute("**/*", intercept)

        return cdn_url[0] if cdn_url else None

    def get_media_url(self, url: str, timeout: int = 30) -> Optional[str]:
        """Navigate to a bunkr file page and extract the media src from the DOM."""
        self._page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        # video: <video src> or <video><source src>
        for selector in ("video[src]", "video source[src]", "source[src]"):
            el = self._page.query_selector(selector)
            if el:
                src = el.get_attribute("src")
                if src and not src.startswith("data:"):
                    return src
        # image: largest <img> that isn't a thumbnail/icon
        for selector in ("img.image-public", "img[src*='cdn']", "main img[src]", "img[src]"):
            el = self._page.query_selector(selector)
            if el:
                src = el.get_attribute("src")
                if src and not src.startswith("data:"):
                    return src
        return None

    def head_content_length(self, url: str, timeout: int = 20) -> Optional[int]:
        try:
            resp = self._context.request.head(url, timeout=timeout * 1000)
            length = resp.headers.get("content-length")
            resp.dispose()
            return int(length) if length else None
        except Exception as exc:
            print(f"[warn] HEAD failed for {url}: {exc}")
            return None

    def download(self, url: str, dest: Path, timeout: int = 30, retries: int = RETRIES) -> None:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0",
            "Referer": "https://bunkr.ru/",
            "Accept": "*/*",
        }
        dest.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(retries):
            existing = dest.stat().st_size if dest.exists() else 0
            if existing:
                headers["Range"] = f"bytes={existing}-"
            else:
                headers.pop("Range", None)

            try:
                with requests.get(url, headers=headers, stream=True, timeout=timeout) as resp:
                    if resp.status_code == 416:
                        print(f"[skip] already complete: {dest.name}")
                        return
                    resp.raise_for_status()

                    total = int(resp.headers.get("Content-Length", 0)) + existing

                    mode = "ab" if existing else "wb"
                    with open(dest, mode) as f:
                        with tqdm(
                                total=total,
                                initial=existing,
                                unit="B",
                                unit_scale=True,
                                unit_divisor=1024,
                                desc=dest.name[:40],
                                leave=True,
                        ) as pbar:
                            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                                if chunk:
                                    f.write(chunk)
                                    pbar.update(len(chunk))
                    return

            except (requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ConnectionError) as e:
                print(f"\n[retry {attempt + 1}/{retries}] {dest.name}: {e}")
                time.sleep(2 ** attempt)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    time.sleep(THROTTLE_HTTP_429_SECS)

        print(f"[moving on] gave up after {retries} attempts: {dest.name}")

    def close(self) -> None:
        self._page.close()
        self._context.close()
        self._browser.close()
        self._pw.stop()

_session: Optional[_Session] = None
class Cache:
    """SQLite-backed cache for search → album URLs and album → file URLs."""
    #a search contains a datetime and all album urls and names found#
    #an album contains a title and file URLs

    def __init__(self, db_path: str = "bunkr_cache.db") -> None:
        self._con = sqlite3.connect(db_path)
        self._con.executescript("""
                                CREATE TABLE IF NOT EXISTS searches
                                (
                                    search_url
                                    TEXT
                                    PRIMARY
                                    KEY,
                                    scraped_at
                                    TEXT
                                    NOT
                                    NULL,
                                    album_urls
                                    TEXT
                                    NOT
                                    NULL
                                    DEFAULT
                                    '[]',
                                    album_names
                                    TEXT
                                    NOT
                                    NULL
                                    DEFAULT
                                    '[]'
                                );
                                CREATE TABLE IF NOT EXISTS albums
                                (
                                    album_url
                                    TEXT
                                    PRIMARY
                                    KEY,
                                    album_title
                                    TEXT
                                    NOT
                                    NULL,
                                    direct_urls
                                    TEXT
                                    NOT
                                    NULL
                                    DEFAULT
                                    '[]',
                                    scraped_at
                                    TEXT
                                    NOT
                                    NULL
                                );
                                CREATE TABLE IF NOT EXISTS album_files
                                (
                                    album_url
                                    TEXT
                                    PRIMARY
                                    KEY,
                                    file_urls
                                    TEXT
                                    NOT
                                    NULL
                                    DEFAULT
                                    '[]',
                                    scraped_at
                                    TEXT
                                    NOT
                                    NULL
                                );
                                """)
        self._con.commit()

    def get_search(self, search_url: str) -> Optional[tuple[list[str], list[str], str]]:
        """Return (album_urls, album_names, scraped_at) or None."""
        row = self._con.execute(
            "SELECT album_urls, album_names, scraped_at FROM searches WHERE search_url = ?",
            (search_url,),
        ).fetchone()
        if row:
            return json.loads(row[0]), json.loads(row[1]), row[2]
        return None

    def set_search(self, search_url: str, album_urls: list[str], album_names: list[str]) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO searches (search_url, scraped_at, album_urls, album_names)"
            " VALUES (?, ?, ?, ?)",
            (search_url, datetime.datetime.now().isoformat(), json.dumps(album_urls), json.dumps(album_names)),
        )
        self._con.commit()

    def get_album(self, album_url: str) -> Optional[tuple[str, list[str], str]]:
        """Return (album_title, direct_urls, scraped_at) or None."""
        row = self._con.execute(
            "SELECT album_title, direct_urls, scraped_at FROM albums WHERE album_url = ?",
            (album_url,),
        ).fetchone()
        if row:
            return row[0], json.loads(row[1]), row[2]
        return None

    def set_album(self, album_url: str, album_title: str, direct_urls: list[str]) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO albums (album_url, album_title, scraped_at, direct_urls)"
            " VALUES (?, ?, ?, ?)",
            (album_url, album_title, datetime.datetime.now().isoformat(), json.dumps(direct_urls)),
        )
        self._con.commit()

    def get_album_files(self, album_url: str) -> Optional[tuple[list[str], str]]:
        """Return (file_urls, scraped_at) or None."""
        row = self._con.execute(
            "SELECT file_urls, scraped_at FROM album_files WHERE album_url = ?",
            (album_url,),
        ).fetchone()
        if row:
            return json.loads(row[0]), row[1]
        return None

    def set_album_files(self, album_url: str, file_urls: list[str]) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO album_files (album_url, scraped_at, file_urls)"
            " VALUES (?, ?, ?)",
            (album_url, datetime.datetime.now().isoformat(), json.dumps(file_urls)),
        )
        self._con.commit()

    def close(self) -> None:
        self._con.close()

class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)
def fetch_html(url: str, timeout: int = 20) -> str:
    assert _session is not None
    return _session.fetch_html(url, timeout=timeout)
def extract_links(html_text: str, base_url: str) -> list[str]:
    parser = LinkExtractor()
    parser.feed(html_text)
    return [urljoin(base_url, link) for link in parser.links]
def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()
def collect_search_pages(search_url: str) -> list[str]:
    queue = [search_url]
    seen = set()
    pages: list[str] = []
    while queue:
        url = queue.pop(0)
        url = normalize_url(url)
        if url in seen:
            continue
        seen.add(url)
        pages.append(url)
        try:
            html_text = fetch_html(url)
        except Exception as exc:
            print(f"[warn] failed to fetch search page {url}: {exc}")
            continue
        for link in extract_links(html_text, url):
            if "balbums.st" in link and "search=" in link and "page=" in link:
                if link not in seen:
                    queue.append(link)
    return pages
def collect_album_links(search_pages: Iterable[str]) -> list[str]:
    albums: set[str] = set()
    for page_url in search_pages:
        try:
            html_text = fetch_html(page_url)
        except Exception as exc:
            print(f"[warn] failed to fetch search page {page_url}: {exc}")
            continue
        for link in extract_links(html_text, page_url):
            if "/a/" in link and "bunkr" in link:
                albums.add(normalize_url(link))
    return sorted(albums)
def collect_album_pages(album_url: str) -> list[str]:
    queue = [album_url]
    seen = set()
    pages: list[str] = []
    while queue:
        url = queue.pop(0)
        url = normalize_url(url)
        if url in seen:
            continue
        seen.add(url)
        pages.append(url)
        try:
            html_text = fetch_html(url)
        except Exception as exc:
            print(f"[warn] failed to fetch album page {url}: {exc}")
            continue
        for link in extract_links(html_text, url):
            if "?page=" in link and urlparse(link).path == urlparse(url).path:
                if link not in seen:
                    queue.append(link)
    return pages
def collect_file_links(album_pages: Iterable[str]) -> list[str]:
    files: set[str] = set()
    for page_url in album_pages:
        try:
            html_text = fetch_html(page_url)
        except Exception as exc:
            print(f"[warn] failed to fetch album page {page_url}: {exc}")
            continue
        for link in extract_links(html_text, page_url):
            if "/f/" in link:
                files.add(normalize_url(link))
    return sorted(files)
@dataclass
class FileInfo:
    file_url: str
    download_url: Optional[str]
    filename: Optional[str]
    size_bytes: Optional[int]
def parse_size(text: str) -> Optional[int]:
    match = re.search(r"([0-9.]+)\s*(KB|MB|GB)", text, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    multiplier = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}[unit]
    return int(value * multiplier)
def parse_file_page(file_url: str) -> FileInfo:
    assert _session is not None
    try:
        download_url = _session.resolve_final_download_url(file_url)
        html_text = _session._page.content()
    except Exception as exc:
        print(f"[warn] failed to fetch file page {file_url}: {exc}")
        return FileInfo(file_url=file_url, download_url=None, filename=None, size_bytes=None)

    title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    filename = None
    if title_match:
        title_text = html.unescape(title_match.group(1)).strip()
        filename = title_text.split("|")[0].strip()

    size_bytes = parse_size(html_text)

    return FileInfo(
        file_url=file_url,
        download_url=download_url,
        filename=filename,
        size_bytes=size_bytes,
    )
def head_content_length(url: str, timeout: int = 20) -> Optional[int]:
    assert _session is not None
    return _session.head_content_length(url, timeout=timeout)
def is_media_file(filename: str | None, download_url: str | None) -> bool:
    candidates = []
    if filename:
        candidates.append(filename)
    if download_url:
        candidates.append(urlparse(download_url).path)
    for name in candidates:
        ext = Path(name).suffix.lower()
        if ext in VIDEO_EXTENSIONS or ext in IMAGE_EXTENSIONS:
            return True
    return False
def sanitize_filename(name: str) -> str:
    name = name.strip().replace("/", "_")
    return re.sub(r"[^A-Za-z0-9._()\- ]+", "_", name)

def download_file(url: str, destination: Path) -> None:
    assert _session is not None
    _session.download(url, destination)
def build_search_url(base_url: str, search_term: str) -> str:
    parsed = urlparse(base_url)
    query = urlencode({"search": search_term})
    return parsed._replace(query=query).geturl()
def create_zip_archive(source_dir: Path, zip_path: Path) -> None:
    import zipfile

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape balbums.st search results and download small videos.",
    )
    parser.add_argument(
        "--search",
        help="Search term for balbums.st")
    parser.add_argument(
        "--search-url",
        help="Full balbums.st search URL (overrides --search)",
    )
    parser.add_argument(
        "--base-url",
        default="https://balbums.st/",
        help="Base URL for balbums.st",
    )
    parser.add_argument(
        "--output",
        default="downloads",
        help="Directory to store downloaded videos",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=None,
        help="Maximum file size in megabytes",
    )
    parser.add_argument(
        "--file-limit",
        type=int,
        default=0,
        help="Limit number of files per album (0 = no limit)",
    )
    parser.add_argument(
        "--album-limit",
        type=int,
        default=0,
        help="Limit number of albums processed (0 = no limit)",
    )

    parser.add_argument(
        "--zip-output",
        help="Optional zip file path to store downloaded files",
    )
    parser.add_argument(
        "--db",
        default="bunkr_cache.db",
        help="SQLite cache database path (default: bunkr_cache.db)",
    )
    parser.add_argument(
        "--update",
        action='store_true', #sets to True if no value in CLI arguments / sys.argv provided
        help="Updated cached file links in sqlite bunkr_cache.db",
    )
    parser.add_argument(
        "--album",
        help="Use link to scrape album."
    )
    args = parser.parse_args()

    if args.update:
        update = True
    else:
        update = False
    if not args.search and not args.search_url and not args.album:
        parser.error("Provide --search or --search-url or --album")

    global _session
    _session = _Session()
    try:
        cache = Cache(args.db)
        if args.album:
            download_album(args.album, Path(OUTPUT_DIR), update=update, cache=cache)
            return True
        if args.search:
            search(args, cache, update=update)
            return True
    finally:
        _session.close()
        _session = None

def download_album(album_url: str, destination: Path,  update: Optional[bool], cache: Optional[Cache]) -> None:
    files_links = []
    #https://bunkr.cr/a/79DncRcK?page=1
    i = 1
    last_count = None
    while True:
        album_page =  f"{album_url}?page={i}"
        album_response = fetch_html(album_page)
        soup = bs4.BeautifulSoup(album_response, "html.parser")
        album_title = soup.find("title").text.replace(" | Bunkr", "")
        file_links_local = [
            "https://bunkr.cr" + link["href"]
            for link in soup.find_all("a", href=True)
            if "/f/" in link["href"]
        ]
        #cache.set_files(album_url, file_links_local)
        files_found = len(file_links_local)
        print(f"[info] found {files_found} files on album page {album_page}")
        if files_found == last_count:
            print(f"[info] quitting search for more count on page {album_page}->{files_found}==count of last page ")
            print(f"[info] total file links: {len(files_links)}")
            break
        files_links.extend(file_links_local)
        i += 1
        last_count = files_found
    cached_files = cache.get_files(album_url)
    if cached_files and not update:
        file_links, scraped_at = cached_files
        print(f"[cache] {len(file_links)} files (cached {scraped_at})")
    else:
        album_pages = collect_album_pages(album_url)
        file_links = collect_file_links(album_pages)
        cache.set_files(album_url, file_links)
    for file_link in set(files_links):
        file_response = fetch_html(file_link)
        soup = bs4.BeautifulSoup(file_response, "html.parser")
        download_links = [link['href'] for link in soup.find_all("a", href=True) if "get" in link['href']]
        if not download_links:
            print(f"[warn] no download link found for {file_link}")
            continue
        cdn_url = _session.resolve_final_download_url(download_links[0])
        if not cdn_url:
            print(f"[warn] could not resolve final URL from {download_links[0]}")
            continue
        filename = sanitize_filename(Path(urlparse(cdn_url).path).name or Path(urlparse(file_link).path).name)
        ext = Path(urlparse(filename).path).suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            dest = Path(f"{OUTPUT_DIR}/{album_title}/vids/{filename}")
        else:
            dest = Path(f"{OUTPUT_DIR}/{album_title}/pics/{filename}")

        print(f"[download] {cdn_url} -> {dest}")
        _session.download(cdn_url, dest)
        print(f"[done] {filename}")

def search(args: argparse.Namespace, cache: Cache, update: bool) -> int:
    search_url = args.search_url or build_search_url(args.base_url, args.search)

    album_urls: list[str] = []
    album_names: list[str] = []

    if not update:
        cached_search = cache.get_search(search_url=search_url)
        if cached_search is None:
            print(f"[cache] no cache found for search_url {search_url}")
        else:
            album_urls, album_names, scraped_at = cached_search
            print(f"[cache] loaded {len(album_urls)} cached album links for search {search_url}")
    #if update is True then here album_urls will be empty list and collect_search_pages will be called
    if not album_urls:
        print(f"[info] collecting search pages from {search_url}")
        search_pages = collect_search_pages(search_url)
        print(f"[info] found {len(search_pages)} search pages")
        album_urls = collect_album_links(search_pages)

    if args.album_limit:
        print(f"[info] limiting search to {args.album_limit}")
        album_urls = album_urls[: args.album_limit]
    print(f"[info] found {len(album_urls)} album links")

    # scrape album titles and bunkr direct URLs if not cached
    bunkr_direct_urls: dict[str, str] = {}  # album_title -> direct_url
    if not album_names:
        for album_page in album_urls:
            try:
                html_text = fetch_html(album_page)
                soup = bs4.BeautifulSoup(html_text, "html.parser")
                album_title = soup.find("h1", class_="truncate").text.strip()
                album_names.append(album_title)
                #a_tags = soup.find_all("a", href=True)
                file_links = [
                    "https://bunkr.cr" + a["href"]
                    for a in soup.find_all("a", href=True)
                    if a["href"].startswith("/f/")
                ]
                print(f"[info] found {len(file_links)} files on {album_page}")
                #caching album
                cache.set_album(album_page, album_title, file_links)
            except Exception as exc:
                print(f"[warn] failed to get bunkr link from {album_page}: {exc}")
                album_names.append("")
        #caching search album_urls and album_titles / names are pararell
        cache.set_search(search_url, album_urls, album_names)
    # rebuild bunkr_direct_urls from cache, regardless if just saved to cache or just loaded from
    for album_page, album_title in zip(album_urls, album_names):
        if album_title:
            bunkr_direct_urls[album_title] = album_page
    print(f"[info] i have {len(bunkr_direct_urls)} album names and links")
    max_bytes = int(args.max_mb * 1024 * 1024) if args.max_mb is not None else None
    #
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- scrape direct bunkr.cr album URLs (with per-album cache) ---
    for index, (album_title, album_url) in enumerate(bunkr_direct_urls.items(), start=1):
        print(f"[info] ({index}/{len(bunkr_direct_urls)}) processing album '{album_title}' {album_url}")

        cached_album = cache.get_album(album_url)
        if cached_album and not args.update:
            _, file_links, scraped_at = cached_album
            print(f"[cache] {len(file_links)} files (cached {scraped_at})")
        else:
            #if update is true album pages and links will be recollected here
            album_pages = collect_album_pages(album_url)
            file_links = collect_file_links(album_pages)
            cache.set_album(album_url, album_title, file_links)

        if args.file_limit:
            file_links = file_links[: args.file_limit]
        print(f"[info] found {len(file_links)} files in album")

        cached_files = cache.get_album_files(album_url)
        if cached_files and not args.update:
            file_links, scraped_at = cached_files
            print(f"[cache] {len(file_links)} files (cached {scraped_at})")
        else:
            album_pages = collect_album_pages(album_url)
            file_links = collect_file_links(album_pages)
            cache.set_album_files(album_url, file_links)

        if args.file_limit:
            file_links = file_links[: args.file_limit]
        print(f"[info] found {len(file_links)} files in album")

        for file_url in file_links:
            info = parse_file_page(file_url)
            if not info.download_url:
                print(f"[warn] no download url for {file_url}")
                continue
            if not is_media_file(info.filename, info.download_url):
                print(f"[skip] not a video/image {info.filename or info.download_url}")
                continue

            size_bytes = info.size_bytes
            if size_bytes is None:
                size_bytes = head_content_length(info.download_url)
            if max_bytes is not None:
                if size_bytes is None:
                    print(f"[skip] unknown size for {info.download_url}")
                    continue
                if size_bytes > max_bytes:
                    print(f"[skip] {info.download_url} size {size_bytes / 1024 / 1024:.2f}MB > limit")
                    continue

            filename = sanitize_filename(info.filename or Path(urlparse(info.download_url).path).name)
            #dest = output_dir / sanitize_filename(album_title or urlparse(album_url).path.strip("/") or "album")
            dest = output_dir / sanitize_filename(album_title)
            dest_file = dest / filename
            dest.mkdir(parents=True, exist_ok=True)

            if dest_file.exists():
                print(f"[skip] already downloaded: {dest_file}")
                continue

            print(f"[download] {info.download_url} -> {dest_file}")
            try:
                if filename.split(".")[-1] in VIDEO_EXTENSIONS:
                    if Path.is_file(dest_file) and is_valid_video(dest_file):
                        print("[info] skipping file download since it is a valid video already")
                    else:
                        download_file(info.download_url, dest_file)
            except Exception as exc:
                print(f"[warn] failed download {info.download_url}: {exc}")
            time.sleep(0.5)

    if args.zip_output:
        zip_path = Path(args.zip_output)
        print(f"[info] creating zip archive at {zip_path}")
        create_zip_archive(output_dir, zip_path)

    cache.close()
    print("[info] done")

if __name__ == "__main__":
    raise SystemExit(main())