python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium

Write-Host ""
$output_dir = Read-Host "Enter output directory (e.g. C:\Media\bunkrr\)"
$throttle = Read-Host "Throttle on HTTP 429 (seconds) [90]"
$retries = Read-Host "Retries [10]"
$check_validity = Read-Host "Check file validity with ffprobe? (True/False) [True]"

if (-not $throttle) { $throttle = "90" }
if (-not $retries) { $retries = "10" }
if (-not $check_validity) { $check_validity = "True" }

@"
OUTPUT_DIR = "$output_dir"

THROTTLE_HTTP_429_SECS = $throttle
RETRIES = $retries

# previously was bunkr-albums.io
CHECK_FILE_VALIDITY = $check_validity  # depends on ffprobe (ffmpeg suite)
"@ | Set-Content config.py

Write-Host ""
Write-Host "config.py written. Run the scraper with:"
Write-Host "  python bunkr_scraper.py --search SEARCH_TERM"