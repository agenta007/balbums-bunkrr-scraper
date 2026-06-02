# balbums.st and bunkr.cr scraper

Automated tool to search and cache album links from [balbums.st](https://balbums.st) and download media files (images and videos) from [bunkr.cr](https://bunkr.cr). Walks each album, caches links and titles.

## Requirements

* Python 3.10+
* Network access
* Playwright (for session and actual download link retrieval)

```
beautifulsoup4
playwright
requests
tqdm
```


# Quick Start

```bash
git clone https://github.com/agenta007/balbums-bunkrr-scraper && cd balbums-bunkrr-scraper
python -m venv venv
```

**Linux/macOS:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

## 1. Install the libraries
```bash
pip install -r requirements.txt
```

## 2. Install the Playwright browser engines (Required!)
```bash
playwright install chromium
```
## 3. Change OUTPUT_DIR in vars.py

# Usage

```bash
python bunkr_scraper.py --search SEARCH_TERM --output /path/to/store/media/
python bunkr_scraper.py --album ALBUM_LINK --output /path/to/store/media/
```
