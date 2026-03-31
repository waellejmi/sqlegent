"""Provider registration for MotherDuck."""

from dbcore.connections.providers.adapter_provider import build_adapter_provider
from dbcore.connections.providers.catalog import register_provider
from dbcore.connections.providers.model import DatabaseProvider, ProviderSpec
from dbcore.connections.providers.motherduck.schema import SCHEMA


def _display_info(config) -> str:
    """Display info for MotherDuck connections."""
    database = config.get_option("database", "") or config.database or ""
    if database:
        return f"md:{database}"
    return "MotherDuck"


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from dbcore.connections.providers.motherduck.adapter import MotherDuckAdapter

    return build_adapter_provider(spec, SCHEMA, MotherDuckAdapter())


SPEC = ProviderSpec(
    db_type="motherduck",
    display_name="MotherDuck",
    schema_path=("dbcore.connections.providers.motherduck.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="",
    requires_auth=True,
    badge_label="MotherDuck",
    url_schemes=("motherduck", "md"),
    provider_factory=_provider_factory,
    display_info=_display_info,
)

register_provider(SPEC)
