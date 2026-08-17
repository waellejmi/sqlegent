import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:

    def load_dotenv():
        return None


load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    ROOT_DIR: Path = Path(__file__).resolve().parent.parent.parent
    RUNTIME_SETTINGS_PATH: Path = ROOT_DIR / ".app_config" / "settings.json"
    # Optional eval-specific runtime settings (overrides applied after RUNTIME_SETTINGS_PATH)
    EVAL_RUNTIME_SETTINGS_PATH: Path = ROOT_DIR / ".app_config" / "eval_settings.json"

    LLM_PROVIDER: str = "groq"
    LLM_MODEL_LIST: list[str] = field(
        default_factory=lambda: [
            "openai/gpt-oss-20b",
            "qwen/qwen3.6-27b",
            "openai/gpt-oss-120b",
            "gemma-4-31b-it",
        ]
    )
    LLM_ACTIVE_MODEL: str = "openai/gpt-oss-20b"

    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    LOG_REQUESTS: bool = False
    LOG_NODE_PAYLOADS: bool = True
    LOG_MAX_CHARS: int = 600
    LOG_MAX_ITEMS: int = 10
    LOG_RESPONSE_MAX_CHARS: int = 300

    ENABLE_ORCHESTRATOR: bool = True
    HUMAN_SQL_REVIEW: bool = False
    EXECUTE_SQL_QUERIES: bool = True
    MAX_SQL_RETRIES: int = 2

    # When True, skip the explain_result node's LLM call and return an empty final_answer.
    # Useful for evaluation runs that only need structured outputs and want to avoid extra LLM calls.
    EXPLAIN_RESULT_NODE_NOT_NEEDED: bool = False

    SHOW_AGENT_GRAPH: bool = False
    SHOW_NODE_HISTORY: bool = True

    METADATA_CACHE_ENABLED: bool = True
    METADATA_CACHE_TTL_SECONDS: int | None = None
    METADATA_CACHE_BYPASS_DEFAULT: bool = False
    METADATA_CACHE_INVALIDATE_DEFAULT: bool = False
    METADATA_CACHE_PATH: Path = ROOT_DIR / ".app_cache" / "metadata_cache.sqlite"

    WEBUI_HISTORY_PATH: Path = ROOT_DIR / ".app_cache" / "webui_history.sqlite"

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

    ASK_RESULT_CONFIRMATION: bool = True

    def __post_init__(self):
        self._load_runtime_settings()

    def _load_runtime_settings(self):
        # Load primary runtime settings
        if self.RUNTIME_SETTINGS_PATH.exists():
            try:
                with open(self.RUNTIME_SETTINGS_PATH, "r") as f:
                    data = json.load(f)

                for key, value in data.items():
                    if hasattr(self, key) and key not in [
                        "ROOT_DIR",
                        "RUNTIME_SETTINGS_PATH",
                    ]:
                        original_val = getattr(self, key)
                        if isinstance(original_val, Path) and value is not None:
                            setattr(self, key, Path(value))
                        else:
                            setattr(self, key, value)
            except Exception as e:
                logger.error(
                    f"Failed to load runtime settings from {self.RUNTIME_SETTINGS_PATH}: {e}"
                )

        # Load optional eval-specific overrides (environment overrides file path if provided)
        eval_path = Path(
            os.environ.get("EVAL_RUNTIME_SETTINGS")
            or str(self.EVAL_RUNTIME_SETTINGS_PATH)
        )
        if eval_path.exists():
            try:
                with open(eval_path, "r") as f:
                    data = json.load(f)

                for key, value in data.items():
                    # Allow eval overrides to modify any runtime setting except ROOT paths
                    if hasattr(self, key) and key not in [
                        "ROOT_DIR",
                        "RUNTIME_SETTINGS_PATH",
                    ]:
                        original_val = getattr(self, key)
                        if isinstance(original_val, Path) and value is not None:
                            setattr(self, key, Path(value))
                        else:
                            setattr(self, key, value)
            except Exception as e:
                logger.error(
                    f"Failed to load eval runtime settings from {eval_path}: {e}"
                )

    def save_runtime_settings(self):
        try:
            self.RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

            data = {}
            for key, value in self.__dict__.items():
                if key in [
                    "ROOT_DIR",
                    "RUNTIME_SETTINGS_PATH",
                    "EVAL_RUNTIME_SETTINGS_PATH",
                ]:
                    continue
                if isinstance(value, Path):
                    data[key] = str(value)
                else:
                    data[key] = value

            with open(self.RUNTIME_SETTINGS_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(
                f"Failed to save runtime settings to {self.RUNTIME_SETTINGS_PATH}: {e}"
            )
            raise

    def save_eval_runtime_settings(self, patch: dict):
        """
        Merge a patch dict into the eval-specific runtime settings file (EVAL_RUNTIME_SETTINGS_PATH
        or path specified by EVAL_RUNTIME_SETTINGS env var). Only keys that are attributes of AppConfig
        will be written.
        """
        eval_path = Path(
            os.environ.get("EVAL_RUNTIME_SETTINGS")
            or str(self.EVAL_RUNTIME_SETTINGS_PATH)
        )
        existing: dict = {}
        if eval_path.exists():
            try:
                with open(eval_path, "r", encoding="utf-8") as f:
                    existing = json.load(f) or {}
            except Exception:
                existing = {}

        merged = dict(existing)
        for k, v in patch.items():
            if hasattr(self, k):
                # store paths as strings
                if isinstance(getattr(self, k), Path) and v is not None:
                    merged[k] = str(v)
                else:
                    merged[k] = v

        eval_path.parent.mkdir(parents=True, exist_ok=True)
        with open(eval_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
