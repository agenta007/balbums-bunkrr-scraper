import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import Cache
from helpers import collect_album_pages, collect_file_links, parse_file_page, sanitize_filename, is_valid_media, download_file, is_media_file, head_content_length
from vars import CHECK_FILE_VALIDITY

def download_album(album_url: str, album_title: str, output_dir: Path, session, cache: Optional[Cache],  args) -> None:
    cached_album = cache.get_album(album_url)
    if cached_album and not args.update:
        _, file_links, scraped_at = cached_album
        print(f"[cache] {len(file_links)} files (cached {scraped_at})")
    else:
        # if update is true album pages and links will be recollected here
        album_pages = collect_album_pages(album_url, session=session)
        file_links = collect_file_links(album_pages, session=session)
        cache.set_album(album_url, album_title, file_links)

    if args.file_limit:
        file_links = file_links[: args.file_limit]
    print(f"[info] found {len(file_links)} files in album")

    cached_files = cache.get_album_files(album_url)
    if cached_files and not args.update:
        file_links, scraped_at = cached_files
        print(f"[cache] {len(file_links)} files (cached {scraped_at})")
    else:
        album_pages = collect_album_pages(album_url, session)
        file_links = collect_file_links(album_pages, session)
        cache.set_album_files(album_url, file_links)

    if args.file_limit:
        file_links = file_links[: args.file_limit]
    print(f"[info] found {len(file_links)} files in album")

    for file_url in file_links:
        info = parse_file_page(file_url, session=session)
        if not info.download_url:
            print(f"[warn] no download url for {file_url}")
            continue
        if not is_media_file(info.filename, info.download_url):
            print(f"[skip] not a video/image {info.filename or info.download_url}")
            continue
        #file
        size_bytes = info.size_bytes
        if size_bytes is None:
            size_bytes = head_content_length(info.download_url)
        if args.max_mb is not None:
            if size_bytes is None:
                print(f"[skip] unknown size for {info.download_url} not comparing to file size limit of {args.max_mb} MB")
                continue
            if size_bytes > args.max_bytes * 1024 * 1024:
                print(f"[skip] {info.download_url} size {size_bytes / 1024 / 1024:.2f}MB > limit")
                continue
        filename = sanitize_filename(info.filename or Path(urlparse(info.download_url).path).name)
        # dest = output_dir / sanitize_filename(album_title or urlparse(album_url).path.strip("/") or "album")
        dest = output_dir / sanitize_filename(album_title)
        dest_file = dest / filename
        dest.mkdir(parents=True, exist_ok=True)
        try:
            if CHECK_FILE_VALIDITY:
                if Path.is_file(dest_file) and is_valid_media(dest_file):
                    print(f"[ffprobe] skipping {filename} since ffprobe detects it's a valid media file")
                    continue
                print(f"[download] {info.download_url} -> {dest_file}")
                download_file(url=info.download_url, session=session, destination=dest_file)
                print(f"[finished] {info.download_url} -> {dest_file}")
        except Exception as exc:
            print(f"[warn] failed download {info.download_url}: {exc}")
        time.sleep(0.5)