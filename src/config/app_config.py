from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    ROOT_DIR: Path = Path(__file__).resolve().parent.parent.parent

    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True
    LOG_REQUESTS: bool = False
    LOG_NODE_PAYLOADS: bool = False
    LOG_MAX_CHARS: int = 600
    LOG_MAX_ITEMS: int = 10
    LOG_RESPONSE_MAX_CHARS: int = 300

    HUMAN_SQL_REVIEW: bool = False
    EXECUTE_SQL_QUERIES: bool = True
    MAX_SQL_RETRIES: int = 1

    SHOW_AGENT_GRAPH: bool = False
    SHOW_NODE_HISTORY: bool = True

    METADATA_CACHE_ENABLED: bool = True
    METADATA_CACHE_TTL_SECONDS: int | None = None
    METADATA_CACHE_BYPASS_DEFAULT: bool = False
    METADATA_CACHE_PATH: Path = ROOT_DIR / ".app_cache" / "metadata_cache.sqlite"

    ENABLE_CONTEXT_LAYER: bool = True
    CONTEXT_PROJECT_ID: str = "default"
    CONTEXT_STORE_PATH: Path = ROOT_DIR / ".app_cache" / "context_layer.sqlite"
    CONTEXT_DEBUG_LOG: bool = False
    CONTEXT_AUTO_INDEX_ON_STARTUP: bool = False
    CONTEXT_REQUIRE_SEMANTIC_PROFILE: bool = True
    CONTEXT_DEFAULT_SEMANTIC_PROFILE: str | None = None

    # List of installed embedding models
    # EMBEDDING_MODEL_NAME: str = "Snowflake/snowflake-arctic-embed-m"
    # EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    # EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_MODEL_NAME: str = "nomic-ai/nomic-embed-text-v1.5"
    EMBEDDING_OFFLINE: bool = True
    EMBEDDING_DEVICE: str = "auto"
    EMBEDDING_NORMALIZE: bool = True
    EMBEDDING_BATCH_SIZE: int = 64

    ENABLE_SCHEMA_CONTEXT: bool = True
    ENABLE_INSTRUCTION_CONTEXT: bool = True
    ENABLE_QUERY_MEMORY: bool = True
    ENABLE_FAILED_QUERY_LOG: bool = False

    MDL_DIR: Path = ROOT_DIR / "semantic"
    MDL_COMMON_SUBDIR: str = "common"
    MDL_DATABASES_SUBDIR: str = "databases"
    MDL_FILE_GLOB: str = "**/*.yaml"
    MDL_BASELINE_FILE: Path = MDL_DIR / "_baseline.generated.yaml"
    MDL_AUTO_GENERATE_BASELINE: bool = True

    SCHEMA_CONTEXT_TOP_K: int = 4
    INSTRUCTION_CONTEXT_TOP_K: int = 2
    QUERY_MEMORY_TOP_K: int = 1

    SCHEMA_CONTEXT_MIN_SIMILARITY: float = 0.45
    INSTRUCTION_CONTEXT_MIN_SIMILARITY: float = 0.55
    QUERY_MEMORY_MIN_SIMILARITY: float = 0.7

    SCHEMA_CONTEXT_MAX_CHARS: int = 8000
    INSTRUCTION_CONTEXT_MAX_CHARS: int = 3000
    QUERY_MEMORY_MAX_CHARS: int = 3000

    QUERY_MEMORY_REQUIRE_VERIFIED: bool = True
    QUERY_MEMORY_REQUIRE_NON_EMPTY: bool = True
    QUERY_MEMORY_MAX_ROWS_PER_DB: int = 5000
    FAILED_QUERY_LOG_MAX_ROWS_PER_DB: int = 20000

    CLI_ASK_RESULT_CONFIRMATION: bool = True
