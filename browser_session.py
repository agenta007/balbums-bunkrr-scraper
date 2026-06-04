import re,time, bs4, requests
from vars import USER_AGENT, COOKIE_LIST
from helpers import is_valid_media
from playwright.sync_api import sync_playwright, Playwright, Browser, Page
from urllib.parse import urlparse, urlunparse, urljoin
from typing import Optional
from vars import THROTTLE_HTTP_429_SECS, RETRIES, VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
from pathlib import Path
from tqdm import tqdm

class Session:
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
        html = self.fetch_html(file_url)
        soup = bs4.BeautifulSoup(html, "html.parser")

        # try jsCDN variable first (direct CDN url in page JS, videos only)
        match = re.search(r'var jsCDN\s*=\s*"([^"]+)"', html)
        if match:
            cdn_url = match.group(1).replace("\\/", "/")
            parsed = urlparse(cdn_url)
            if parsed.scheme and parsed.netloc and parsed.path and parsed.path != "/":
                signed = self._sign_cdn_url(cdn_url)
                if signed:
                    return signed

        # fallback 1: btn-main download button
        btn = soup.find("a", class_=lambda c: c and "btn-main" in c)
        if btn and btn.get("href"):
            href = btn["href"].replace("\\/", "/").split("#")[0]
            if href.startswith("http"):
                return href
            return urljoin(file_url, href)

        # fallback 2: #download-btn
        dl_btn = soup.find(id="download-btn")
        if dl_btn:
            href = dl_btn.get("href", "").replace("\\/", "/").split("#")[0]
            if href and href.startswith("http"):
                return href
            data_id = dl_btn.get("data-id")
            if data_id:
                return f"https://get.bunkrr.su/file/{data_id}"

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
                        print(f"[skip] response code was 416: {dest.name}")
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
                    print(f"[HTTP_ERROR] 429: Too Many Requests. Waiting {THROTTLE_HTTP_429_SECS} seconds.")
                    time.sleep(THROTTLE_HTTP_429_SECS)
        print(f"[moving on] gave up after {retries} attempts: {dest.name}")

    def close(self) -> None:
        self._page.close()
        self._context.close()
        self._browser.close()
        self._pw.stop()