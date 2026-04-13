import json
import pathlib
from dataclasses import dataclass


@dataclass
class DBConfig:
    ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent.parent
    DEFAULT_SQLITE_PATH: pathlib.Path = ROOT_DIR / "data" / "Chinook.db"
    CONFIG_DIR: pathlib.Path = ROOT_DIR / ".app_config"
    CONFIG_FILE: pathlib.Path = CONFIG_DIR / "config.json"
    ACTIVE_DATABASE_URI_KEY: str = "database_uri"

    def default_database_uri(self) -> str:
        return self.sqlite_path_to_uri(self.DEFAULT_SQLITE_PATH)

    def sqlite_path_to_uri(self, db_path: pathlib.Path | str) -> str:
        path = pathlib.Path(db_path).expanduser().resolve()
        return f"sqlite:///{path}"

    def _ensure_config_dir(self) -> None:
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def save_config(self, data: dict) -> None:
        self._ensure_config_dir()
        self.CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_config(self) -> dict:
        if not self.CONFIG_FILE.exists():
            return {}
        try:
            raw = self.CONFIG_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
        return {}

    def get_database_uri(self) -> str:
        config = self.load_config()
        uri = config.get(self.ACTIVE_DATABASE_URI_KEY)
        if isinstance(uri, str) and uri.strip():
            return uri.strip()
        return self.default_database_uri()

    def set_database_uri(self, uri: str) -> None:
        clean_uri = uri.strip()
        if not clean_uri:
            raise ValueError("Database URI cannot be empty.")
        config = self.load_config()
        config[self.ACTIVE_DATABASE_URI_KEY] = clean_uri
        self.save_config(config)
