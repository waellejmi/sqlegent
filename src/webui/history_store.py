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
    db_name: str | None
    db_dialect: str | None
    session_id: str | None


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
                    is_saved INTEGER DEFAULT 0,
                    db_name TEXT,
                    session_id TEXT,
                    db_dialect TEXT
                )
                """
            )
            try:
                conn.execute(
                    "ALTER TABLE webui_chat_history ADD COLUMN is_saved INTEGER DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # column already exists
            try:
                conn.execute("ALTER TABLE webui_chat_history ADD COLUMN db_name TEXT")
                conn.execute("ALTER TABLE webui_chat_history ADD COLUMN db_dialect TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE webui_chat_history ADD COLUMN session_id TEXT")
            except sqlite3.OperationalError:
                pass
            
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webui_chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT,
                    token_total INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            try:
                conn.execute(
                    "ALTER TABLE webui_chat_sessions ADD COLUMN token_total INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass

    def add_interaction(
        self,
        question: str,
        sql: str | None,
        db_output: str | None,
        answer: str | None,
        db_name: str | None = None,
        db_dialect: str | None = None,
        session_id: str | None = None,
    ) -> str:
        record_id = str(uuid.uuid4())
        created_at = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO webui_chat_history (id, question, sql, db_output, answer, created_at, db_name, db_dialect, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (record_id, question, sql, db_output, answer, created_at, db_name, db_dialect, session_id),
            )
            return record_id

    def get_history(self, session_id: str | None = None, limit: int = 50) -> list[ChatHistoryRecord]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, question, sql, db_output, answer, created_at, is_saved, db_name, db_dialect, session_id
                FROM webui_chat_history
                WHERE (? IS NULL OR session_id = ?)
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (session_id, session_id, limit,),
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

    def get_sessions(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT h.session_id, MAX(h.created_at) as last_active, COUNT(h.id) as interaction_count, 
                       COALESCE(s.title, (SELECT question FROM webui_chat_history w2 WHERE w2.session_id = h.session_id ORDER BY created_at ASC LIMIT 1)) as title,
                       COALESCE(s.token_total, 0) as token_total
                FROM webui_chat_history h
                LEFT JOIN webui_chat_sessions s ON h.session_id = s.session_id
                WHERE h.session_id IS NOT NULL
                GROUP BY h.session_id
                ORDER BY last_active DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def rename_session(self, session_id: str, title: str):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO webui_chat_sessions (session_id, title)
                VALUES (?, ?)
                ON CONFLICT(session_id) DO UPDATE SET title=excluded.title
                """,
                (session_id, title)
            )

    def increment_session_tokens(self, session_id: str, delta_tokens: int) -> int:
        if delta_tokens <= 0:
            return self.get_session_token_total(session_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO webui_chat_sessions (session_id, token_total)
                VALUES (?, ?)
                ON CONFLICT(session_id) DO UPDATE
                SET token_total = webui_chat_sessions.token_total + excluded.token_total
                """,
                (session_id, delta_tokens),
            )
            row = conn.execute(
                "SELECT token_total FROM webui_chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return int(row[0]) if row else 0

    def get_session_token_total(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(token_total, 0) FROM webui_chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return int(row[0]) if row else 0

    def delete_session(self, session_id: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM webui_chat_history WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM webui_chat_sessions WHERE session_id = ?", (session_id,))
