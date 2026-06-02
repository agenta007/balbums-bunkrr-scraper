#!/bin/bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

echo ""
read -p "Enter output directory (e.g. /mnt/raid/bunkrr/): " output_dir
read -p "Throttle on HTTP 429 (seconds) [90]: " throttle
read -p "Retries [10]: " retries
read -p "Check file validity with ffprobe? (True/False) [True]: " check_validity

throttle=${throttle:-90}
retries=${retries:-10}
check_validity=${check_validity:-True}

cat > config.py << EOF
OUTPUT_DIR = "$output_dir"

THROTTLE_HTTP_429_SECS = $throttle
RETRIES = $retries

# previously was bunkr-albums.io
CHECK_FILE_VALIDITY = $check_validity  # depends on ffprobe (ffmpeg suite)
EOF

echo ""
echo "config.py written. Run the scraper with:"
echo "  python bunkr_scraper.py --search SEARCH_TERM"