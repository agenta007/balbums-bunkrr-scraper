import sqlite3
import json
import datetime
from typing import Optional

class Cache:
    """SQLite-backed cache for search → album URLs and album → file URLs."""
    #a search contains a datetime and all album urls and names found#
    #an album contains a title and file URLs

    def __init__(self, db_path: str = "bunkr_cache.db") -> None:
        self._con = sqlite3.connect(db_path)
        self._con.executescript("""
                                CREATE TABLE IF NOT EXISTS searches
                                (
                                    search_url
                                    TEXT
                                    PRIMARY
                                    KEY,
                                    scraped_at
                                    TEXT
                                    NOT
                                    NULL,
                                    album_urls
                                    TEXT
                                    NOT
                                    NULL
                                    DEFAULT
                                    '[]',
                                    album_names
                                    TEXT
                                    NOT
                                    NULL
                                    DEFAULT
                                    '[]'
                                );
                                CREATE TABLE IF NOT EXISTS albums
                                (
                                    album_url
                                    TEXT
                                    PRIMARY
                                    KEY,
                                    album_title
                                    TEXT
                                    NOT
                                    NULL,
                                    direct_urls
                                    TEXT
                                    NOT
                                    NULL
                                    DEFAULT
                                    '[]',
                                    scraped_at
                                    TEXT
                                    NOT
                                    NULL
                                );
                                CREATE TABLE IF NOT EXISTS album_files
                                (
                                    album_url
                                    TEXT
                                    PRIMARY
                                    KEY,
                                    file_urls
                                    TEXT
                                    NOT
                                    NULL
                                    DEFAULT
                                    '[]',
                                    scraped_at
                                    TEXT
                                    NOT
                                    NULL
                                );
                                """)
        self._con.commit()

    def get_search(self, search_url: str) -> Optional[tuple[list[str], list[str], str]]:
        """Return (album_urls, album_names, scraped_at) or None."""
        row = self._con.execute(
            "SELECT album_urls, album_names, scraped_at FROM searches WHERE search_url = ?",
            (search_url,),
        ).fetchone()
        if row:
            return json.loads(row[0]), json.loads(row[1]), row[2]
        return None

    def set_search(self, search_url: str, album_urls: list[str], album_names: list[str]) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO searches (search_url, scraped_at, album_urls, album_names)"
            " VALUES (?, ?, ?, ?)",
            (search_url, datetime.datetime.now().isoformat(), json.dumps(album_urls), json.dumps(album_names)),
        )
        self._con.commit()

    def get_album(self, album_url: str) -> Optional[tuple[str, list[str], str]]:
        """Return (album_title, direct_urls, scraped_at) or None."""
        row = self._con.execute(
            "SELECT album_title, direct_urls, scraped_at FROM albums WHERE album_url = ?",
            (album_url,),
        ).fetchone()
        if row:
            return row[0], json.loads(row[1]), row[2]
        return None

    def set_album(self, album_url: str, album_title: str, direct_urls: list[str]) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO albums (album_url, album_title, scraped_at, direct_urls)"
            " VALUES (?, ?, ?, ?)",
            (album_url, album_title, datetime.datetime.now().isoformat(), json.dumps(direct_urls)),
        )
        self._con.commit()

    def get_album_files(self, album_url: str) -> Optional[tuple[list[str], str]]:
        """Return (file_urls, scraped_at) or None."""
        row = self._con.execute(
            "SELECT file_urls, scraped_at FROM album_files WHERE album_url = ?",
            (album_url,),
        ).fetchone()
        if row:
            return json.loads(row[0]), row[1]
        return None

    def set_album_files(self, album_url: str, file_urls: list[str]) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO album_files (album_url, scraped_at, file_urls)"
            " VALUES (?, ?, ?)",
            (album_url, datetime.datetime.now().isoformat(), json.dumps(file_urls)),
        )
        self._con.commit()

    def close(self) -> None:
        self._con.close()
