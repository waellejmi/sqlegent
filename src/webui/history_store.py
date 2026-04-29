import sqlite3
import time
import uuid
from typing import TypedDict

from config.app_config import AppConfig


class ChatHistoryRecord(TypedDict):
    id: str
    question: str
    sql: str | None
    db_output: str | None
    answer: str | None
    created_at: int
    is_saved: int


class HistoryStore:
    def __init__(self, config: AppConfig | None = None):
        self._config = config or AppConfig()
        self._db_path = self._config.WEBUI_HISTORY_PATH
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self._db_path, timeout=5)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webui_chat_history (
                    id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    sql TEXT,
                    db_output TEXT,
                    answer TEXT,
                    created_at INTEGER NOT NULL,
                    is_saved INTEGER DEFAULT 0
                )
                """
            )
            try:
                conn.execute(
                    "ALTER TABLE webui_chat_history ADD COLUMN is_saved INTEGER DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # column already exists

    def add_interaction(
        self,
        question: str,
        sql: str | None,
        db_output: str | None,
        answer: str | None,
    ) -> str:
        record_id = str(uuid.uuid4())
        created_at = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO webui_chat_history (id, question, sql, db_output, answer, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (record_id, question, sql, db_output, answer, created_at),
            )
            return record_id

    def get_history(self, limit: int = 50) -> list[ChatHistoryRecord]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, question, sql, db_output, answer, created_at, is_saved
                FROM webui_chat_history
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]  # type: ignore

    def mark_saved(self, history_id: str, status: int = 1):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE webui_chat_history
                SET is_saved = ?
                WHERE id = ?
                """,
                (
                    status,
                    history_id,
                ),
            )

    def delete_interaction(self, history_id: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM webui_chat_history WHERE id = ?", (history_id,))
