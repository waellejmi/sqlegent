"""Provider registration."""

from dbcore.connections.providers.adapter_provider import build_adapter_provider
from dbcore.connections.providers.catalog import register_provider
from dbcore.connections.providers.model import DatabaseProvider, ProviderSpec
from dbcore.connections.providers.snowflake.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from dbcore.connections.providers.snowflake.adapter import SnowflakeAdapter

    return build_adapter_provider(spec, SCHEMA, SnowflakeAdapter())

SPEC = ProviderSpec(
    db_type="snowflake",
    display_name="Snowflake",
    schema_path=("dbcore.connections.providers.snowflake.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="",
    requires_auth=True,
    badge_label="SNOW",
    provider_factory=_provider_factory,
)

register_provider(SPEC)
