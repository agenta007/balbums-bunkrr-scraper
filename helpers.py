import hashlib
import subprocess
import html
from urllib.parse import urlparse, urljoin, urlencode
import requests
import bs4
from typing import Optional, Iterable
import re
from LinkExtractor import LinkExtractor
from FileInfo import FileInfo
from vars import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
from pathlib import Path
def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def is_valid_media(path):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-i', path],
        capture_output=True
    )
    return result.returncode == 0

def get_album_title(album_url: str) -> Optional[str]:
    response = requests.get(album_url)
    soup = bs4.BeautifulSoup(response.text, "html.parser")
    h1 = soup.find("h1", class_="truncate")
    return h1.text.strip() if h1 else None

def parse_size(text: str) -> Optional[int]:
    match = re.search(r"([0-9.]+)\s*(KB|MB|GB)", text, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    multiplier = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}[unit]
    return int(value * multiplier)

def parse_file_page(file_url: str, session) -> FileInfo:
    try:
        download_url = session.resolve_final_download_url(file_url)
        html_text = session._page.content()
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
def head_content_length(url: str, session, timeout: int = 20) -> Optional[int]:
    assert session is not None
    return session.head_content_length(url, timeout=timeout)
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

def download_file(url: str, session, destination: Path) -> None:
    session.download(url, destination)
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

def extract_links(html_text: str, base_url: str) -> list[str]:
    parser = LinkExtractor()
    parser.feed(html_text)
    return [urljoin(base_url, link) for link in parser.links]
def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()

def collect_search_pages(search_url: str, session) -> list[str]:
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
            html_text =  session.fetch_html(url)
        except Exception as exc:
            print(f"[warn] failed to fetch search page {url}: {exc}")
            continue
        for link in extract_links(html_text, url):
            if "balbums.st" in link and "search=" in link and "page=" in link:
                if link not in seen:
                    queue.append(link)
    return pages
def collect_album_links(search_pages: Iterable[str], session) -> list[str]:
    albums: set[str] = set()
    for page_url in search_pages:
        try:
            html_text = session.fetch_html(page_url)
        except Exception as exc:
            print(f"[warn] failed to fetch search page {page_url}: {exc}")
            continue
        for link in extract_links(html_text, page_url):
            if "/a/" in link and "bunkr" in link:
                albums.add(normalize_url(link))
    return sorted(albums)
def collect_album_pages(album_url: str, session) -> list[str]:
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
            html_text = session.fetch_html(url)
        except Exception as exc:
            print(f"[warn] failed to fetch album page {url}: {exc}")
            continue
        for link in extract_links(html_text, url):
            if "?page=" in link and urlparse(link).path == urlparse(url).path:
                if link not in seen:
                    queue.append(link)
    return pages

def collect_file_links(album_pages: Iterable[str], session) -> list[str]:
    files: set[str] = set()
    for page_url in album_pages:
        try:
            html_text = session.fetch_html(page_url)
        except Exception as exc:
            print(f"[warn] failed to fetch album page {page_url}: {exc}")
            continue
        for link in extract_links(html_text, page_url):
            if "/f/" in link:
                files.add(normalize_url(link))
    return sorted(files)

