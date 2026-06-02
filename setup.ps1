Write-Host "Creating virtual environment..." -ForegroundColor Cyan
python -m venv venv

Write-Host "Activating virtual environment..." -ForegroundColor Cyan
.\venv\Scripts\Activate.ps1

Write-Host "Installing dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host "Installing Playwright browser engine..." -ForegroundColor Cyan
python -m playwright install firefox

Write-Host ""
Write-Host "Configuration" -ForegroundColor Yellow
Write-Host "-------------" -ForegroundColor Yellow
$output_dir = Read-Host "Enter output directory (e.g. C:\Media\bunkrr\)"
$throttle = Read-Host "Throttle on HTTP 429 (seconds) [90]"
$retries = Read-Host "Retries [10]"
$check_validity = Read-Host "Check file validity with ffprobe? (True/False) [True]"
$user_agent = Read-Host "User agent [Mozilla/5.0 (X11; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0]"

if (-not $throttle) { $throttle = "90" }
if (-not $retries) { $retries = "10" }
if (-not $check_validity) { $check_validity = "True" }

Write-Host "Writing vars.py..." -ForegroundColor Cyan
@"
OUTPUT_DIR = "$output_dir"

THROTTLE_HTTP_429_SECS = $throttle
RETRIES = $retries

# previously was bunkr-albums.io
CHECK_FILE_VALIDITY = $check_validity  # depends on ffprobe (ffmpeg suite)
"@ | Set-Content vars.py
USER_AGENT = "$user_agent"
"@ | Set-Content vars.py

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "Run the scraper with:" -ForegroundColor Green
Write-Host "  python bunkr_scraper.py --search SEARCH_TERM" -ForegroundColor White
Write-Host "  python bunkr_scraper.py --album ALBUM_LINK" -ForegroundColor White