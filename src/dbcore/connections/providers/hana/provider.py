"""Provider registration."""

from dbcore.connections.providers.adapter_provider import build_adapter_provider
from dbcore.connections.providers.catalog import register_provider
from dbcore.connections.providers.hana.schema import SCHEMA
from dbcore.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from dbcore.connections.providers.hana.adapter import HanaAdapter

    return build_adapter_provider(spec, SCHEMA, HanaAdapter())


SPEC = ProviderSpec(
    db_type="hana",
    display_name="SAP HANA",
    schema_path=("dbcore.connections.providers.hana.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="30015",
    requires_auth=True,
    badge_label="HANA",
    url_schemes=("hana", "saphana"),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
