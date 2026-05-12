import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from config.app_config import AppConfig

_conn = None
_checkpointer = None

def get_checkpointer():
    global _conn, _checkpointer
    if _checkpointer is None:
        db_path = AppConfig().ROOT_DIR / ".app_cache" / "checkpoints.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(db_path, check_same_thread=False)
        _checkpointer = SqliteSaver(_conn)
        _checkpointer.setup()
    return _checkpointer

_async_conn = None
_async_checkpointer = None

async def get_async_checkpointer():
    global _async_conn, _async_checkpointer
    if _async_checkpointer is None:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        db_path = AppConfig().ROOT_DIR / ".app_cache" / "checkpoints.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _async_conn = await aiosqlite.connect(db_path)
        _async_checkpointer = AsyncSqliteSaver(_async_conn)
        await _async_checkpointer.setup()
    return _async_checkpointer

