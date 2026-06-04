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
from Cache import Cache
from browser_session import Session
from download_album import download_album
from search import search
from helpers import get_album_title
from vars import OUTPUT_DIR
from pathlib import Path

_session = Session()

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
        default=OUTPUT_DIR,
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

    try:
        cache = Cache(args.db)
        if args.max_mb is not None:
            print(f"Set maximum file size in megabytes = {args.max_mb} MB / {int(args.max_mb) * 1024 * 1024} B")
        if args.album:
            album_title = get_album_title(args.album)
            output_dir = None
            if args.output:
                output_dir = Path(args.output)
            else:
                output_dir = Path(OUTPUT_DIR)
            download_album(album_url=args.album, album_title=album_title, output_dir=output_dir, session=_session, cache=cache, args=args)
            return True
        if args.search:
            search(args, cache, update=update, session=_session)
            return True
    finally:
        _session.close()

if __name__ == "__main__":
    raise SystemExit(main())