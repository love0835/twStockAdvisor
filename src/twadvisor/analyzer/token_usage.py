"""Token usage logging."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


def record_token_usage(db_path: str, provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Persist token usage into a lightweight SQLite table."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO token_usage (provider, model, prompt_tokens, completion_tokens, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (provider, model, prompt_tokens, completion_tokens, datetime.utcnow().isoformat()),
        )
        connection.commit()
    finally:
        connection.close()
