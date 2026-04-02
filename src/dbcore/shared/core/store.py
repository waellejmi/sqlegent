"""Base store class with common JSON file operations."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("SQLIT_CONFIG_DIR", Path.home() / ".sqlit"))


class JSONFileStore:
    def __init__(self, file_path: Path):
        self._file_path = file_path

    @property
    def file_path(self) -> Path:
        return self._file_path

    def _ensure_dir(self) -> None:
        dir_path = self._file_path.parent
        dir_path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(dir_path, 0o700)
        except OSError:
            pass

    def _read_json(self) -> Any:
        if not self._file_path.exists():
            return None
        try:
            with open(self._file_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return None

    def _write_json(self, data: Any) -> None:
        self._ensure_dir()
        fd, tmp_path = tempfile.mkstemp(
            dir=self._file_path.parent,
            prefix=".tmp_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._file_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def exists(self) -> bool:
        return self._file_path.exists()
