# balbums.st and bunkr.cr Scraper

Automated tool to search and cache album links from [balbums.st](https://balbums.st) and download media files (images and videos) from [bunkr.cr](https://bunkr.cr). Walks each album, caches links and titles.

## Requirements

* Python 3.10+
* Network access
* ffprobe / ffmpeg (optional, for file validity checks)
* Playwright (for resolving actual download links)

```
beautifulsoup4
playwright
requests
tqdm
```

## Quick Start

Clone the repo first:

```bash
git clone https://github.com/agenta007/balbums-bunkrr-scraper && cd balbums-bunkrr-scraper
```

Then run the setup script for your platform:

**Linux/macOS:**
```bash
bash setup.sh
```

**Windows:**
```powershell
.\setup.ps1
```

The setup script will install dependencies, install the Playwright browser engine, and prompt you to configure `vars.py`.

## Manual Setup

Activate the virtual environment:

**Linux/macOS:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install the Playwright browser engine:

```bash
python -m playwright install firefox
```

Edit `config.py` and set `OUTPUT_DIR` to your desired media output location.

## Usage

```bash
python bunkr_scraper.py --search SEARCH_TERM
python bunkr_scraper.py --album ALBUM_LINK

usage: bunkr_scraper.py [-h] [--search SEARCH] [--search-url SEARCH_URL] [--base-url BASE_URL] [--output OUTPUT] [--max-mb MAX_MB]
                        [--file-limit FILE_LIMIT] [--album-limit ALBUM_LIMIT] [--zip-output ZIP_OUTPUT] [--db DB] [--update]
                        [--album ALBUM]

Scrape balbums.st search results and download small videos.

options:
  -h, --help            show this help message and exit
  --search SEARCH       Search term for balbums.st
  --search-url SEARCH_URL
                        Full balbums.st search URL (overrides --search)
  --base-url BASE_URL   Base URL for balbums.st
  --output OUTPUT       Directory to store downloaded videos
  --max-mb MAX_MB       Maximum file size in megabytes
  --file-limit FILE_LIMIT
                        Limit number of files per album (0 = no limit)
  --album-limit ALBUM_LIMIT
                        Limit number of albums processed (0 = no limit)
  --zip-output ZIP_OUTPUT
                        Optional zip file path to store downloaded files
  --db DB               SQLite cache database path (default: bunkr_cache.db)
  --update              Updated cached file links in sqlite bunkr_cache.db
  --album ALBUM         Use link to scrape album.
```