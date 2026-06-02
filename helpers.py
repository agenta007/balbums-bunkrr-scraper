import hashlib
def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()
import subprocess
def is_valid_video(path):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-i', path],
        capture_output=True
    )
    return result.returncode == 0