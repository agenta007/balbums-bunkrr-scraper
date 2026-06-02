#!/bin/bash
set -e

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Installing Playwright browser engine..."
python -m playwright install firefox

echo ""
echo "Configuration"
echo "-------------"
read -p "Enter output directory (e.g. /mnt/raid/bunkrr/): " output_dir
read -p "Throttle on HTTP 429 (seconds) [90]: " throttle
read -p "Retries [10]: " retries
read -p "Check file validity with ffprobe? (True/False) [True]: " check_validity
read -p "User agent [Mozilla/5.0 (X11; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0]: " user_agent

throttle=${throttle:-90}
retries=${retries:-10}
check_validity=${check_validity:-True}

echo "Writing vars.py..."
cat > vars.py << EOF
OUTPUT_DIR = "$output_dir"

THROTTLE_HTTP_429_SECS = $throttle
RETRIES = $retries

# previously was bunkr-albums.io
CHECK_FILE_VALIDITY = $check_validity  # depends on ffprobe (ffmpeg suite)
USER_AGENT = "$user_agent"
EOF

echo ""
echo "Setup complete!"
echo "Run the scraper with:"
echo "  python bunkr_scraper.py --search SEARCH_TERM"
echo "  python bunkr_scraper.py --album ALBUM_LINK"