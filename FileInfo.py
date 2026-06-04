from dataclasses import dataclass
from typing import Optional
@dataclass
class FileInfo:
    file_url: str
    download_url: Optional[str]
    filename: Optional[str]
    size_bytes: Optional[int]