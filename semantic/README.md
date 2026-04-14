# Semantic Layer (MDL-lite)

This folder contains optional YAML files used by sqlgent context layer.

Context indexing merges two sources:
- Live database baseline introspection (auto-generated)
- Manual YAML overrides in this directory

Baseline file:
- `_baseline.generated.yaml` (auto-created by reindex when enabled)

You can add one or more YAML files. Top-level keys:
- `models`
- `relationships`
- `instructions`

## Example

```yaml
models:
  - name: Invoice
    description: Customer invoices for billing.
    aliases: [bill, billing]
    columns:
      - name: Total
        description: Invoice total amount in local currency.

relationships:
  - from_model: Invoice
    to_model: Customer
    type: many_to_one
    join:
      from_column: CustomerId
      to_column: CustomerId
    description: Invoice belongs to one customer.

instructions:
  - id: default_sql_style
    scope: sql
    is_default: true
    instruction: Use business-approved joins and avoid selecting unused columns.
```

## Notes

- Manual files always override baseline descriptions/aliases/column metadata.
- Metrics/calculated fields are planned for phase 2.
- Reindex command:
  - `python src/main.py --context-reindex`
- Stats command:
  - `python src/main.py --context-stats`
