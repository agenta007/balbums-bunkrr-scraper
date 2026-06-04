import argparse
import bs4
import Cache
from helpers import build_search_url, collect_search_pages, collect_album_links, create_zip_archive
from pathlib import Path
from download_album import download_album

def search(args: argparse.Namespace, cache: Cache, update: bool, session):
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
        search_pages = collect_search_pages(search_url, session=session)
        print(f"[info] found {len(search_pages)} search pages")
        album_urls = collect_album_links(search_pages, session=session)
    if args.album_limit:
        print(f"[info] limiting search to {args.album_limit}")
        album_urls = album_urls[: args.album_limit]
    print(f"[info] found {len(album_urls)} album links")
    # scrape album titles and bunkr direct URLs if not cached
    bunkr_direct_urls: dict[str, str] = {}  # album_title -> direct_url
    if not album_names:
        for album_page in album_urls:
            try:
                html_text = session.fetch_html(album_page)
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
                print(f"[info] cached album {album_title} which has {len(file_links)} files link: {album_page}")
            except Exception as exc:
                print(f"[warn] failed to get bunkr link from {album_page}: {exc}")
                album_names.append("")
        #caching search album_urls and album_titles / names are pararell
        cache.set_search(search_url, album_urls, album_names)
    # rebuild bunkr_direct_urls from cache, regardless if just saved to cache or just loaded from
    for album_page, album_title in zip(album_urls, album_names):
        if album_title:
            bunkr_direct_urls[album_title] = album_page
    print(f"[info] I have {len(bunkr_direct_urls)} album names and album links")
    max_bytes = int(args.max_mb * 1024 * 1024) if args.max_mb is not None else None
    #
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- scrape direct bunkr.cr album URLs (with per-album cache) ---
    for index, (album_title, album_url) in enumerate(bunkr_direct_urls.items(), start=1):
        print(f"[info] ({index}/{len(bunkr_direct_urls)}) processing album '{album_title}' {album_url}")
        download_album(album_url=album_url, album_title=album_title, output_dir=output_dir, cache=cache, session=session, args=args)

    if args.zip_output:
        zip_path = Path(args.zip_output)
        print(f"[info] creating zip archive at {zip_path}")
        create_zip_archive(output_dir, zip_path)

    cache.close()
    print("[info] done")