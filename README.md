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

Run the setup script for your platform:

**Linux/macOS:**
```bash
bash setup.sh
```

**Windows:**
```powershell
.\setup.ps1
```

The setup script will install dependencies, install the Playwright browser engine, and prompt you to configure `config.py`.

## Manual Setup

Clone the repo and create a virtual environment:

```bash
git clone https://github.com/agenta007/balbums-bunkrr-scraper && cd balbums-bunkrr-scraper
python -m venv venv
```

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
python -m playwright install chromium
```

Edit `config.py` and set `OUTPUT_DIR` to your desired media output location.

## Usage

```bash
python bunkr_scraper.py --search SEARCH_TERM
python bunkr_scraper.py --album ALBUM_LINK
```