USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0"
COOKIE_LIST = [] #currently not used, not needed
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".avif"}
OUTPUT_DIR = "/mnt/raid/.bunkr/" #edit this to your location
THROTTLE_HTTP_429_SECS = 90
RETRIES = 10
BASE_SEARCH_URL = "https://balbums.st/?search=SEARCH_TERM&mode=broad&per=20&sort=latest" # previously was bunkr-albums.io
CHECK_FILE_VALIDITY = True #depends on ffprobe (ffmpeg suite)