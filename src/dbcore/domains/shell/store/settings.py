"""Settings store for managing application settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dbcore.shared.core.store import CONFIG_DIR, JSONFileStore


def _resolve_settings_path() -> Path:
    override = os.environ.get("SQLIT_SETTINGS_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return CONFIG_DIR / "settings.json"


class SettingsStore(JSONFileStore):
    _instance: SettingsStore | None = None
    _instance_path: Path | None = None

    def __init__(self, file_path: Path | None = None) -> None:
        super().__init__(file_path or _resolve_settings_path())

    @classmethod
    def get_instance(cls) -> SettingsStore:
        path = _resolve_settings_path()
        if cls._instance is None or cls._instance_path != path:
            cls._instance = cls(file_path=path)
            cls._instance_path = path
        return cls._instance

    def load_all(self) -> dict[str, Any]:
        data = self._read_json()
        return data if isinstance(data, dict) else {}

    def save_all(self, settings: dict[str, Any]) -> None:
        self._write_json(settings)

    def get(self, key: str, default: Any = None) -> Any:
        return self.load_all().get(key, default)

    def set(self, key: str, value: Any) -> None:
        settings = self.load_all()
        settings[key] = value
        self.save_all(settings)

    def delete(self, key: str) -> bool:
        settings = self.load_all()
        if key in settings:
            del settings[key]
            self.save_all(settings)
            return True
        return False
