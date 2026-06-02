#balbums.st and bunkrr.cr Scraper

This repository provides automated way to search and cache albums links from `https://balbums.st/`` and to download media files (images and videos) from``https://bunkr.cr`, walk each album, cache links and titles.

# Quick Start
````````git clone https://github.com/agenta007/balbums-bunkrr-scraper && cd balbums-bunkrr-scraper```
```````python -m venv venv```

**Linux/macOS:**
``````source venv/bin/activate```

**Windows:**
`````venv\Scripts\activate```

# 1. Install the libraries
````pip install -r requirements.txt```

# 2. Install the Playwright browser engines (Required!)
```playwright install chromium```

## Requirements

* Python 3.10+
* Network access
* Playwright (for session and actual download link retrieval)

```
beautifulsoup4
playwright
requests
tqdm
````
`````

# Usage
```python /path/to/script/bunkr_scraper.py --search SEARCH_TERM --output /path/to/store/media/```
```python /path/to/script/bunkr_scraper.py --album ALBUM_LINK --output /path/to/store/media/``` 

## Notes

* The scraper checks file size from the file page and falls back to a `HEAD` request.
* Files with unknown size or over the limit are skipped.
* Only common video extensions are downloaded (mp4, mkv, webm, mov, avi, wmv, m4v).
