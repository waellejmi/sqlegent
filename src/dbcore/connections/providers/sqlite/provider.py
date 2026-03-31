"""Provider registration."""

from dbcore.connections.providers.adapter_provider import build_adapter_provider
from dbcore.connections.providers.catalog import register_provider
from dbcore.connections.providers.model import DatabaseProvider, ProviderSpec
from dbcore.connections.providers.sqlite.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from dbcore.connections.providers.sqlite.adapter import SQLiteAdapter

    return build_adapter_provider(spec, SCHEMA, SQLiteAdapter())

SPEC = ProviderSpec(
    db_type="sqlite",
    display_name="SQLite",
    schema_path=("dbcore.connections.providers.sqlite.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=True,
    has_advanced_auth=False,
    default_port="",
    requires_auth=True,
    badge_label="SQLite",
    url_schemes=("sqlite",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
