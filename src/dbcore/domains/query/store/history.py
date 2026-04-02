"""History store for managing query history per connection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from dbcore.shared.core.store import CONFIG_DIR, JSONFileStore


@dataclass
class QueryHistoryEntry:
    query: str
    timestamp: str
    connection_name: str
    is_starred: bool = False
    is_starred_only: bool = False

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "timestamp": self.timestamp,
            "connection_name": self.connection_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> QueryHistoryEntry:
        return cls(
            query=data["query"],
            timestamp=data["timestamp"],
            connection_name=data["connection_name"],
        )


class HistoryStore(JSONFileStore):
    MAX_ENTRIES_PER_CONNECTION = 100

    def __init__(self) -> None:
        super().__init__(CONFIG_DIR / "query_history.json")

    def _load_all_entries(self) -> list[dict]:
        data = self._read_json()
        return data if isinstance(data, list) else []

    def load_for_connection(self, connection_name: str) -> list[QueryHistoryEntry]:
        all_entries = self._load_all_entries()
        try:
            entries = [
                QueryHistoryEntry.from_dict(entry)
                for entry in all_entries
                if entry.get("connection_name") == connection_name
            ]
            entries.sort(key=lambda e: e.timestamp, reverse=True)
            return entries
        except (KeyError, TypeError):
            return []

    def load_all(self) -> list[QueryHistoryEntry]:
        all_entries = self._load_all_entries()
        try:
            entries = [QueryHistoryEntry.from_dict(entry) for entry in all_entries]
            entries.sort(key=lambda e: e.timestamp, reverse=True)
            return entries
        except (KeyError, TypeError):
            return []

    def save_query(self, connection_name: str, query: str) -> None:
        all_entries = self._load_all_entries()
        query_stripped = query.strip()
        now = datetime.now().isoformat()

        for entry in all_entries:
            if (
                entry.get("connection_name") == connection_name
                and entry.get("query", "").strip() == query_stripped
            ):
                entry["timestamp"] = now
                break
        else:
            new_entry = QueryHistoryEntry(
                query=query_stripped,
                timestamp=now,
                connection_name=connection_name,
            )
            all_entries.append(new_entry.to_dict())

        connection_entries = [
            e for e in all_entries if e.get("connection_name") == connection_name
        ]
        other_entries = [
            e for e in all_entries if e.get("connection_name") != connection_name
        ]

        connection_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        connection_entries = connection_entries[: self.MAX_ENTRIES_PER_CONNECTION]

        self._write_json(other_entries + connection_entries)

    def delete_entry(self, connection_name: str, timestamp: str) -> bool:
        all_entries = self._load_all_entries()
        original_count = len(all_entries)

        all_entries = [
            e
            for e in all_entries
            if not (
                e.get("timestamp") == timestamp
                and e.get("connection_name") == connection_name
            )
        ]

        if len(all_entries) < original_count:
            self._write_json(all_entries)
            return True
        return False

    def clear_for_connection(self, connection_name: str) -> int:
        all_entries = self._load_all_entries()
        original_count = len(all_entries)

        all_entries = [
            e for e in all_entries if e.get("connection_name") != connection_name
        ]

        deleted = original_count - len(all_entries)
        if deleted > 0:
            self._write_json(all_entries)
        return deleted
