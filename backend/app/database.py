from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str):
        self.path = path
        self._memory_connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self.path == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False)
                self._memory_connection.row_factory = sqlite3.Row
                self._memory_connection.execute("PRAGMA foreign_keys = ON")
            return self._memory_connection
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS clusters (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    primary_url TEXT NOT NULL,
                    title_language TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
                    source_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL UNIQUE,
                    published_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    keywords_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS refresh_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    fetched INTEGER NOT NULL,
                    inserted INTEGER NOT NULL,
                    clustered INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS translation_cache (
                    cache_key TEXT PRIMARY KEY,
                    source_language TEXT NOT NULL,
                    target_language TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS translation_usage_monthly (
                    provider TEXT NOT NULL,
                    year_month TEXT NOT NULL,
                    used_characters INTEGER NOT NULL DEFAULT 0,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, year_month)
                );

                CREATE TABLE IF NOT EXISTS manual_refresh_usage (
                    window_key TEXT PRIMARY KEY,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_clusters_published_at ON clusters(published_at DESC);
                CREATE INDEX IF NOT EXISTS idx_articles_cluster_id ON articles(cluster_id);
                CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at DESC);
                CREATE INDEX IF NOT EXISTS idx_translation_cache_languages ON translation_cache(source_language, target_language);
                """
            )
            self._ensure_column(connection, "articles", "content", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "clusters", "title_language", "TEXT")

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str) -> Any:
    return json.loads(value)
