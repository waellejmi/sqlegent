"""Provider registration."""

from dbcore.connections.providers.adapter_provider import build_adapter_provider
from dbcore.connections.providers.catalog import register_provider
from dbcore.connections.providers.db2.schema import SCHEMA
from dbcore.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from dbcore.connections.providers.db2.adapter import Db2Adapter

    return build_adapter_provider(spec, SCHEMA, Db2Adapter())


SPEC = ProviderSpec(
    db_type="db2",
    display_name="IBM Db2",
    schema_path=("dbcore.connections.providers.db2.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="50000",
    requires_auth=True,
    badge_label="Db2",
    url_schemes=("db2",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
