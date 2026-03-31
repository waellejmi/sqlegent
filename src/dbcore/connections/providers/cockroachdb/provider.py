"""Provider registration."""

from dbcore.connections.providers.adapter_provider import build_adapter_provider
from dbcore.connections.providers.catalog import register_provider
from dbcore.connections.providers.cockroachdb.schema import SCHEMA
from dbcore.connections.providers.docker import DockerDetector
from dbcore.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from dbcore.connections.providers.cockroachdb.adapter import CockroachDBAdapter

    return build_adapter_provider(spec, SCHEMA, CockroachDBAdapter())

SPEC = ProviderSpec(
    db_type="cockroachdb",
    display_name="CockroachDB",
    schema_path=("dbcore.connections.providers.cockroachdb.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="26257",
    requires_auth=False,
    badge_label="CRDB",
    url_schemes=("cockroachdb", "cockroach"),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("cockroachdb",),
        env_vars={
            "user": ("COCKROACH_USER",),
            "password": ("COCKROACH_PASSWORD",),
            "database": ("COCKROACH_DATABASE",),
        },
        default_user="root",
    ),
)

register_provider(SPEC)
