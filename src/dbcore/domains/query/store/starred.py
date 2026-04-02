"""Starred queries store for managing favorite queries per connection."""

from __future__ import annotations

from dbcore.shared.core.store import CONFIG_DIR, JSONFileStore


class StarredStore(JSONFileStore):
    _instance: StarredStore | None = None

    def __init__(self) -> None:
        super().__init__(CONFIG_DIR / "starred_queries.json")

    @classmethod
    def get_instance(cls) -> StarredStore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_all(self) -> dict[str, list[str]]:
        data = self._read_json()
        return data if isinstance(data, dict) else {}

    def load_all(self) -> dict[str, set[str]]:
        all_starred = self._load_all()
        result: dict[str, set[str]] = {}
        for connection_name, queries in all_starred.items():
            if not isinstance(queries, list):
                continue
            result[connection_name] = {q.strip() for q in queries}
        return result

    def load_for_connection(self, connection_name: str) -> set[str]:
        all_starred = self._load_all()
        queries = all_starred.get(connection_name, [])
        return {q.strip() for q in queries}

    def is_starred(self, connection_name: str, query: str) -> bool:
        starred = self.load_for_connection(connection_name)
        return query.strip() in starred

    def star_query(self, connection_name: str, query: str) -> bool:
        all_starred = self._load_all()
        query_stripped = query.strip()

        if connection_name not in all_starred:
            all_starred[connection_name] = []

        if query_stripped in all_starred[connection_name]:
            return False

        all_starred[connection_name].append(query_stripped)
        self._write_json(all_starred)
        return True

    def unstar_query(self, connection_name: str, query: str) -> bool:
        all_starred = self._load_all()
        query_stripped = query.strip()

        if connection_name not in all_starred:
            return False

        if query_stripped not in all_starred[connection_name]:
            return False

        all_starred[connection_name].remove(query_stripped)

        if not all_starred[connection_name]:
            del all_starred[connection_name]

        self._write_json(all_starred)
        return True

    def toggle_star(self, connection_name: str, query: str) -> bool:
        if self.is_starred(connection_name, query):
            self.unstar_query(connection_name, query)
            return False
        self.star_query(connection_name, query)
        return True

    def clear_for_connection(self, connection_name: str) -> int:
        all_starred = self._load_all()

        if connection_name not in all_starred:
            return 0

        count = len(all_starred[connection_name])
        del all_starred[connection_name]
        self._write_json(all_starred)
        return count
