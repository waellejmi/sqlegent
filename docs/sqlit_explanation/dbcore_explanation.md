# dbcore explanation

This document explains `src/dbcore` by logical flow and then maps **every Python file**.

You asked to avoid repeating the same explanation for replica files (for example every DB adapter), so this doc does:
- explain canonical patterns once,
- then mark replica files as "same pattern as X".

## 1) Logical architecture: how everything connects

Flow (high level):

1. `connections/domain` defines what a connection is (`ConnectionConfig`, endpoint/tunnel/auth concepts).
2. `connections/providers` defines DB capabilities and plug-in registration (schema + adapter + provider metadata).
3. `connections/discovery` finds candidate connections (Docker and cloud) and converts them to domain configs.
4. `connections/app` orchestrates runtime actions (URL parsing, session lifecycle, persistence and credentials workflow).
5. `connections/store` persists named connections and credential references.
6. `shared/app` wires runtime services.
7. `ui` renders forms/screens/controllers on top of app + provider + discovery layers.
8. `tests` validate discovery and connection behavior.

Dependency direction is mostly one-way:

`domain -> providers -> discovery/app -> ui -> tests`

## 2) Pattern primer (explained once)

### Provider triplet pattern

Most DB providers follow the same 3-file structure:

- `provider.py`: registers metadata + factory + docker detector config.
- `adapter.py`: actual driver behavior (connect/query/introspection/dialect).
- `schema.py`: form/config schema fields and validation shape.

Canonical references:

- provider pattern: `src/dbcore/connections/providers/postgresql/provider.py`
- adapter pattern: `src/dbcore/connections/providers/postgresql/adapter.py`
- schema pattern: `src/dbcore/connections/providers/postgresql/schema.py`

All provider replicas listed later are variants of this pattern.

### UI picker tab pattern

Connection picker tabs are split into:

- `tabs/connections.py` (saved connections),
- `tabs/docker.py` (docker-discovered),
- `tabs/cloud.py` (cloud-discovered),
- controller files that load/filter data and feed the tab views.

## 3) File-by-file map (every file)

## 3.1 `src/dbcore/connections` core

- `src/dbcore/connections/__init__.py` - package marker.
- `src/dbcore/connections/domain/__init__.py` - domain package marker.
- `src/dbcore/connections/domain/config.py` - core config models and normalization/serialization helpers.
- `src/dbcore/connections/domain/passwords.py` - rules for when DB/SSH passwords are required.

### app orchestration

- `src/dbcore/connections/app/__init__.py` - app package marker.
- `src/dbcore/connections/app/cloud_actions.py` - executes cloud actions in connection picker flows.
- `src/dbcore/connections/app/connection_flow.py` - prompts/populates missing credentials and sequences connection readiness.
- `src/dbcore/connections/app/credentials.py` - keyring/plaintext/in-memory credential backends.
- `src/dbcore/connections/app/executor.py` - serialized DB operation executor.
- `src/dbcore/connections/app/install_strategy.py` - computes install strategy for missing drivers.
- `src/dbcore/connections/app/installer.py` - package installation workflow.
- `src/dbcore/connections/app/persist_utils.py` - persistence safety helpers (avoid accidental password loss).
- `src/dbcore/connections/app/save_connection.py` - save/rename/update helpers for connection configs.
- `src/dbcore/connections/app/session.py` - connection session lifecycle (connect/switch/close/tunnel cleanup).
- `src/dbcore/connections/app/tunnel.py` - SSH tunnel creation and dependency checks.
- `src/dbcore/connections/app/url_parser.py` - parses DB URLs into `ConnectionConfig`.

### app mocks/test scaffolding

- `src/dbcore/connections/app/mock_adapter_core.py` - mock cursor/connection core.
- `src/dbcore/connections/app/mock_data.py` - fake dataset generation.
- `src/dbcore/connections/app/mock_default_adapters.py` - default mock adapters per DB type.
- `src/dbcore/connections/app/mock_profiles.py` - predefined mock connection profiles.
- `src/dbcore/connections/app/mock_provider.py` - mock provider factory.
- `src/dbcore/connections/app/mock_settings.py` - parse mock settings JSON to runtime shape.
- `src/dbcore/connections/app/mocks.py` - central mock profile declarations.

### cli

- `src/dbcore/connections/cli/__init__.py` - CLI package marker.
- `src/dbcore/connections/cli/commands.py` - CLI commands for listing/saving/testing connections.
- `src/dbcore/connections/cli/helpers.py` - schema-aware CLI parsing helpers.
- `src/dbcore/connections/cli/prompts.py` - interactive CLI prompts for passwords/fields.

### discovery

- `src/dbcore/connections/discovery/__init__.py` - discovery package marker.
- `src/dbcore/connections/discovery/docker_detector.py` - Docker scan/status/credential extraction/conversion.
- `src/dbcore/connections/discovery/cloud/__init__.py` - cloud discovery package exports.
- `src/dbcore/connections/discovery/cloud/base.py` - cloud provider interfaces and shared types.
- `src/dbcore/connections/discovery/cloud/mock.py` - mock cloud discovery states.
- `src/dbcore/connections/discovery/cloud/registry.py` - cloud provider registry.

#### cloud/aws

- `src/dbcore/connections/discovery/cloud/aws/__init__.py` - AWS discovery package marker.
- `src/dbcore/connections/discovery/cloud/aws/cache.py` - AWS discovery cache IO.
- `src/dbcore/connections/discovery/cloud/aws/provider.py` - AWS DB discovery/provider behavior.

#### cloud/azure

- `src/dbcore/connections/discovery/cloud/azure/__init__.py` - Azure discovery package marker.
- `src/dbcore/connections/discovery/cloud/azure/cache.py` - Azure discovery cache IO.
- `src/dbcore/connections/discovery/cloud/azure/cli.py` - Azure CLI wrappers.
- `src/dbcore/connections/discovery/cloud/azure/discovery.py` - Azure resource discovery logic.
- `src/dbcore/connections/discovery/cloud/azure/firewall.py` - Azure firewall helpers and error detection.
- `src/dbcore/connections/discovery/cloud/azure/models.py` - Azure discovery models.
- `src/dbcore/connections/discovery/cloud/azure/provider.py` - Azure cloud provider integration.

#### cloud/gcp

- `src/dbcore/connections/discovery/cloud/gcp/__init__.py` - GCP discovery package marker.
- `src/dbcore/connections/discovery/cloud/gcp/cache.py` - GCP discovery cache IO.
- `src/dbcore/connections/discovery/cloud/gcp/provider.py` - GCP Cloud SQL discovery/provider logic.

### store

- `src/dbcore/connections/store/__init__.py` - store package exports.
- `src/dbcore/connections/store/connections.py` - persistent JSON connection store + credential interaction.
- `src/dbcore/connections/store/memory.py` - in-memory non-persistent store.

## 3.2 `src/dbcore/connections/providers` non-replica infrastructure

- `src/dbcore/connections/providers/__init__.py` - provider package exports.
- `src/dbcore/connections/providers/adapter_provider.py` - wraps adapter+schema into full provider object.
- `src/dbcore/connections/providers/catalog.py` - provider discovery/registration/catalog lookup.
- `src/dbcore/connections/providers/config_service.py` - normalize/validate config through provider.
- `src/dbcore/connections/providers/docker.py` - provider-side docker detector model.
- `src/dbcore/connections/providers/driver.py` - driver import checks and missing-driver behavior.
- `src/dbcore/connections/providers/exceptions.py` - provider/driver exception types.
- `src/dbcore/connections/providers/explorer_nodes.py` - explorer node provider abstraction for UI tree.
- `src/dbcore/connections/providers/metadata.py` - convenience accessors for provider metadata.
- `src/dbcore/connections/providers/model.py` - provider protocols/spec/capability data model.
- `src/dbcore/connections/providers/registry.py` - compatibility shim over catalog APIs.
- `src/dbcore/connections/providers/schema_catalog.py` - schema catalog compatibility layer.
- `src/dbcore/connections/providers/schema_helpers.py` - schema field builders and common schema pieces.
- `src/dbcore/connections/providers/tls.py` - TLS-related normalization/options helpers.
- `src/dbcore/connections/providers/validation.py` - schema-driven config validator.
- `src/dbcore/connections/providers/adapters/__init__.py` - adapter base package marker.
- `src/dbcore/connections/providers/adapters/base.py` - base adapter class and shared adapter contracts.
- `src/dbcore/connections/providers/postgresql/base.py` - PostgreSQL-family shared behavior.
- `src/dbcore/connections/providers/mysql/base.py` - MySQL-family shared behavior.

## 3.3 `src/dbcore/connections/providers` provider replicas (all files)

Replica note: each set below follows the canonical provider/adapter/schema pattern.

### athena
- `src/dbcore/connections/providers/athena/__init__.py` - package marker.
- `src/dbcore/connections/providers/athena/provider.py` - provider registration (replica pattern).
- `src/dbcore/connections/providers/athena/adapter.py` - adapter implementation (replica pattern).
- `src/dbcore/connections/providers/athena/schema.py` - schema definition (replica pattern).

### bigquery
- `src/dbcore/connections/providers/bigquery/__init__.py`
- `src/dbcore/connections/providers/bigquery/provider.py`
- `src/dbcore/connections/providers/bigquery/adapter.py`
- `src/dbcore/connections/providers/bigquery/schema.py`

### clickhouse
- `src/dbcore/connections/providers/clickhouse/__init__.py`
- `src/dbcore/connections/providers/clickhouse/provider.py`
- `src/dbcore/connections/providers/clickhouse/adapter.py`
- `src/dbcore/connections/providers/clickhouse/schema.py`

### cockroachdb
- `src/dbcore/connections/providers/cockroachdb/__init__.py`
- `src/dbcore/connections/providers/cockroachdb/provider.py`
- `src/dbcore/connections/providers/cockroachdb/adapter.py`
- `src/dbcore/connections/providers/cockroachdb/schema.py`

### d1
- `src/dbcore/connections/providers/d1/__init__.py`
- `src/dbcore/connections/providers/d1/provider.py`
- `src/dbcore/connections/providers/d1/adapter.py`
- `src/dbcore/connections/providers/d1/schema.py`

### db2
- `src/dbcore/connections/providers/db2/__init__.py`
- `src/dbcore/connections/providers/db2/provider.py`
- `src/dbcore/connections/providers/db2/adapter.py`
- `src/dbcore/connections/providers/db2/schema.py`

### duckdb
- `src/dbcore/connections/providers/duckdb/__init__.py`
- `src/dbcore/connections/providers/duckdb/provider.py`
- `src/dbcore/connections/providers/duckdb/adapter.py`
- `src/dbcore/connections/providers/duckdb/schema.py`

### firebird
- `src/dbcore/connections/providers/firebird/__init__.py`
- `src/dbcore/connections/providers/firebird/provider.py`
- `src/dbcore/connections/providers/firebird/adapter.py`
- `src/dbcore/connections/providers/firebird/schema.py`

### flight
- `src/dbcore/connections/providers/flight/__init__.py`
- `src/dbcore/connections/providers/flight/provider.py`
- `src/dbcore/connections/providers/flight/adapter.py`
- `src/dbcore/connections/providers/flight/schema.py`

### hana
- `src/dbcore/connections/providers/hana/__init__.py`
- `src/dbcore/connections/providers/hana/provider.py`
- `src/dbcore/connections/providers/hana/adapter.py`
- `src/dbcore/connections/providers/hana/schema.py`

### mariadb
- `src/dbcore/connections/providers/mariadb/__init__.py`
- `src/dbcore/connections/providers/mariadb/provider.py`
- `src/dbcore/connections/providers/mariadb/adapter.py`
- `src/dbcore/connections/providers/mariadb/schema.py`

### motherduck
- `src/dbcore/connections/providers/motherduck/__init__.py`
- `src/dbcore/connections/providers/motherduck/provider.py`
- `src/dbcore/connections/providers/motherduck/adapter.py`
- `src/dbcore/connections/providers/motherduck/schema.py`

### mssql
- `src/dbcore/connections/providers/mssql/__init__.py`
- `src/dbcore/connections/providers/mssql/provider.py`
- `src/dbcore/connections/providers/mssql/adapter.py`
- `src/dbcore/connections/providers/mssql/schema.py`

### mysql
- `src/dbcore/connections/providers/mysql/__init__.py`
- `src/dbcore/connections/providers/mysql/provider.py`
- `src/dbcore/connections/providers/mysql/adapter.py`
- `src/dbcore/connections/providers/mysql/schema.py`

### oracle
- `src/dbcore/connections/providers/oracle/__init__.py`
- `src/dbcore/connections/providers/oracle/provider.py`
- `src/dbcore/connections/providers/oracle/adapter.py`
- `src/dbcore/connections/providers/oracle/schema.py`

### oracle_legacy
- `src/dbcore/connections/providers/oracle_legacy/__init__.py`
- `src/dbcore/connections/providers/oracle_legacy/provider.py`
- `src/dbcore/connections/providers/oracle_legacy/adapter.py`
- `src/dbcore/connections/providers/oracle_legacy/schema.py`

### postgresql (canonical full example)
- `src/dbcore/connections/providers/postgresql/__init__.py` - package marker.
- `src/dbcore/connections/providers/postgresql/provider.py` - canonical provider registration.
- `src/dbcore/connections/providers/postgresql/adapter.py` - canonical adapter implementation.
- `src/dbcore/connections/providers/postgresql/schema.py` - canonical schema definition.

### presto
- `src/dbcore/connections/providers/presto/__init__.py`
- `src/dbcore/connections/providers/presto/provider.py`
- `src/dbcore/connections/providers/presto/adapter.py`
- `src/dbcore/connections/providers/presto/schema.py`

### redshift
- `src/dbcore/connections/providers/redshift/__init__.py`
- `src/dbcore/connections/providers/redshift/provider.py`
- `src/dbcore/connections/providers/redshift/adapter.py`
- `src/dbcore/connections/providers/redshift/schema.py`

### snowflake
- `src/dbcore/connections/providers/snowflake/__init__.py`
- `src/dbcore/connections/providers/snowflake/provider.py`
- `src/dbcore/connections/providers/snowflake/adapter.py`
- `src/dbcore/connections/providers/snowflake/schema.py`

### spanner
- `src/dbcore/connections/providers/spanner/__init__.py`
- `src/dbcore/connections/providers/spanner/provider.py`
- `src/dbcore/connections/providers/spanner/adapter.py`
- `src/dbcore/connections/providers/spanner/schema.py`

### sqlite
- `src/dbcore/connections/providers/sqlite/__init__.py`
- `src/dbcore/connections/providers/sqlite/provider.py`
- `src/dbcore/connections/providers/sqlite/adapter.py`
- `src/dbcore/connections/providers/sqlite/schema.py`

### supabase
- `src/dbcore/connections/providers/supabase/__init__.py`
- `src/dbcore/connections/providers/supabase/provider.py`
- `src/dbcore/connections/providers/supabase/adapter.py`
- `src/dbcore/connections/providers/supabase/schema.py`

### teradata
- `src/dbcore/connections/providers/teradata/__init__.py`
- `src/dbcore/connections/providers/teradata/provider.py`
- `src/dbcore/connections/providers/teradata/adapter.py`
- `src/dbcore/connections/providers/teradata/schema.py`

### trino
- `src/dbcore/connections/providers/trino/__init__.py`
- `src/dbcore/connections/providers/trino/provider.py`
- `src/dbcore/connections/providers/trino/adapter.py`
- `src/dbcore/connections/providers/trino/schema.py`

### turso
- `src/dbcore/connections/providers/turso/__init__.py`
- `src/dbcore/connections/providers/turso/provider.py`
- `src/dbcore/connections/providers/turso/adapter.py`
- `src/dbcore/connections/providers/turso/schema.py`

## 3.4 `src/dbcore/shared`

- `src/dbcore/shared/app/runtime.py` - runtime config dataclasses.
- `src/dbcore/shared/app/services.py` - service container/build functions and dependency wiring.

## 3.5 `src/dbcore/ui` (screens/controllers/forms)

### top-level ui modules

- `src/dbcore/ui/__init__.py` - UI package marker.
- `src/dbcore/ui/connection_error_handlers.py` - maps errors to user-facing UI handling.
- `src/dbcore/ui/connection_focus.py` - form focus/navigation behavior.
- `src/dbcore/ui/connection_form.py` - form state + field composition controller.
- `src/dbcore/ui/connection_test_controller.py` - test-connection action controller.
- `src/dbcore/ui/driver_status.py` - formatting/install hints for driver status.
- `src/dbcore/ui/driver_status_controller.py` - checks driver readiness and updates status.
- `src/dbcore/ui/field_widgets.py` - widget constructors for field definitions.
- `src/dbcore/ui/fields.py` - connection form field definitions and grouping.
- `src/dbcore/ui/restart_cache.py` - cache for reconnect/restart UX state.
- `src/dbcore/ui/validation.py` - validation state and rule execution.
- `src/dbcore/ui/validation_ui_binder.py` - binds validation result to UI controls.

### mixins

- `src/dbcore/ui/mixins/__init__.py` - mixin package marker.
- `src/dbcore/ui/mixins/connection.py` - main connection management mixin used by app UI.

### screens (general)

- `src/dbcore/ui/screens/__init__.py` - screens package marker.
- `src/dbcore/ui/screens/azure_firewall.py` - firewall helper screen for Azure SQL.
- `src/dbcore/ui/screens/connection.py` - primary create/edit connection screen.
- `src/dbcore/ui/screens/connection_styles.py` - style constants for connection screens.
- `src/dbcore/ui/screens/folder_input.py` - folder naming/input dialog screen.
- `src/dbcore/ui/screens/install_progress.py` - package installation progress screen.
- `src/dbcore/ui/screens/package_setup.py` - missing-driver setup/install screen.
- `src/dbcore/ui/screens/password_input.py` - password prompt dialog screen.

### connection picker

- `src/dbcore/ui/screens/connection_picker/__init__.py` - picker package marker.
- `src/dbcore/ui/screens/connection_picker/cloud_nodes.py` - cloud tree node models/helpers.
- `src/dbcore/ui/screens/connection_picker/constants.py` - picker constants.
- `src/dbcore/ui/screens/connection_picker/screen.py` - full picker screen orchestration.
- `src/dbcore/ui/screens/connection_picker/shortcuts.py` - keyboard shortcut definitions.
- `src/dbcore/ui/screens/connection_picker/state.py` - picker state models.
- `src/dbcore/ui/screens/connection_picker/view.py` - picker rendering helpers.

#### picker controllers

- `src/dbcore/ui/screens/connection_picker/controllers/__init__.py` - controller package marker.
- `src/dbcore/ui/screens/connection_picker/controllers/cloud.py` - cloud tab controller logic.
- `src/dbcore/ui/screens/connection_picker/controllers/docker.py` - docker tab controller logic.

#### picker tabs

- `src/dbcore/ui/screens/connection_picker/tabs/__init__.py` - tabs package marker.
- `src/dbcore/ui/screens/connection_picker/tabs/cloud.py` - cloud tab item building/filtering.
- `src/dbcore/ui/screens/connection_picker/tabs/connections.py` - saved connection tab item building.
- `src/dbcore/ui/screens/connection_picker/tabs/docker.py` - docker tab item building/filtering.

#### picker cloud provider ui adapters

- `src/dbcore/ui/screens/connection_picker/cloud_providers/__init__.py` - cloud provider UI adapter package marker.
- `src/dbcore/ui/screens/connection_picker/cloud_providers/base.py` - base interface for cloud UI adapters.
- `src/dbcore/ui/screens/connection_picker/cloud_providers/aws.py` - AWS-specific UI adapter.
- `src/dbcore/ui/screens/connection_picker/cloud_providers/azure.py` - Azure-specific UI adapter.
- `src/dbcore/ui/screens/connection_picker/cloud_providers/gcp.py` - GCP-specific UI adapter.
- `src/dbcore/ui/screens/connection_picker/cloud_providers/utils.py` - shared cloud UI adapter helpers.

## 3.6 `src/dbcore/tests`

- `src/dbcore/tests/test_docker_detector.py` - core docker detector tests.
- `src/dbcore/tests/test_database_docker.py` - docker-backed DB behavior tests.
- `src/dbcore/tests/unit/test_docker_credential_parsing.py` - unit tests for credential extraction.
- `src/dbcore/tests/unit/test_docker_tab_filtering.py` - unit tests for docker picker tab filtering.
- `src/dbcore/tests/integration/docker_detect/__init__.py` - integration test package marker.
- `src/dbcore/tests/integration/docker_detect/conftest.py` - integration fixtures/config.
- `src/dbcore/tests/integration/docker_detect/database_configs.py` - test DB container definitions.
- `src/dbcore/tests/integration/docker_detect/test_all_databases.py` - all-DB integration docker detection tests.
- `src/dbcore/tests/integration/docker_detect/test_docker_detection.py` - end-to-end docker detection integration tests.

## 4) Practical reading order (to understand architecture fastest)

Read in this order:

1. `src/dbcore/connections/domain/config.py`
2. `src/dbcore/connections/providers/model.py`
3. `src/dbcore/connections/providers/catalog.py`
4. `src/dbcore/connections/providers/adapter_provider.py`
5. `src/dbcore/connections/providers/postgresql/provider.py`
6. `src/dbcore/connections/providers/postgresql/adapter.py`
7. `src/dbcore/connections/discovery/docker_detector.py`
8. `src/dbcore/connections/app/url_parser.py`
9. `src/dbcore/connections/app/session.py`
10. `src/dbcore/connections/store/connections.py`
11. `src/dbcore/ui/screens/connection.py`
12. `src/dbcore/ui/screens/connection_picker/screen.py`
13. `src/dbcore/tests/test_docker_detector.py`

That sequence gives you the logical model first, then runtime orchestration, then UI wiring, then behavior verification.
