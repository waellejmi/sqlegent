from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    ROOT_DIR: Path = Path(__file__).resolve().parent.parent.parent
    EXECUTE_SQL_QUERIES: bool = True
    HUMAN_SQL_REVIEW: bool = True
    MAX_SQL_RETRIES: int = 1
    SHOW_AGENT_GRAPH: bool = False
    SHOW_NODE_HISTORY: bool = True
    METADATA_CACHE_ENABLED: bool = True
    METADATA_CACHE_TTL_SECONDS: int | None = None
    METADATA_CACHE_BYPASS_DEFAULT: bool = False
    METADATA_CACHE_PATH: Path = ROOT_DIR / ".app_cache" / "metadata_cache.sqlite"
