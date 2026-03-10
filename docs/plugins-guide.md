# Official Plugins Guide

Eva ships four official plugins. Each is a separate package; install only what
you need.

---

## Installing

```sh
pip install eva-postgres
pip install eva-otlp
pip install eva-a2a
pip install eva-mcp
```

EE-only plugins (requires `eva-ee`):

```sh
pip install eva-agntcy
```

---

## eva-postgres

PostgreSQL storage adapter — replaces the default SQLite backend.

### Config

```python
from eva_postgres.adapter import PostgresStorageAdapter

adapter = PostgresStorageAdapter(url="postgresql://user:pass@host/dbname")
adapter.setup()        # creates tables (idempotent)
adapter.save_run(run)
run = adapter.get_run("run_id")
```

### Environment

No dedicated env var. Pass `url` directly, or read from `DATABASE_URL`:

```python
import os
adapter = PostgresStorageAdapter(url=os.environ["DATABASE_URL"])
```

### Tables

Single table `eva_runs` with columns: `run_id`, `dataset`, `target`,
`started_at`, `duration_ms`, `passed`, `results_json`.

---

## eva-otlp

OTLP trace exporter — pipes Eva spans to any OTEL-compatible backend
(Jaeger, Datadog, Grafana Tempo).

### Config

```python
from eva_otlp.exporter import OtlpExporter

exporter = OtlpExporter(endpoint="http://collector:4317")
exporter.setup()   # installs global TracerProvider; call once at startup
```

### Environment

| Variable | Description |
|----------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector endpoint (read by `OtlpExporter`) |

Default endpoint: `http://localhost:4317` (gRPC).

### Integration

Call `exporter.setup()` before `eva serve` starts (e.g. in a startup hook or
custom entrypoint). Eva emits spans under the `eva.*` namespace.

---

## eva-a2a

Import A2A Agent Cards as Eva contract YAML files.

### CLI

```sh
eva-a2a convert agent-card.json --output-dir ./contracts
```

- `agent-card.json`: path to A2A Agent Card JSON file.
- `--output-dir`: destination for generated YAML files (default: `contracts/`).
- One YAML file produced per skill in `card["skills"]`.
- Contract named `<agent-name>.<skill-name>`.

### Programmatic

```python
from eva_a2a.importer import import_agent_card, contracts_to_yaml

card = json.loads(Path("agent-card.json").read_text())
contracts = import_agent_card(card)
paths = contracts_to_yaml(contracts, output_dir=Path("contracts"))
```

### See Also

Full integration workflow: [A2A + MCP Integration Guide](a2a-mcp-guide.md).

---

## eva-mcp

Import MCP server manifests as Eva contract YAML files.

### CLI

```sh
eva-mcp convert mcp-manifest.json --output-dir ./contracts
```

- `mcp-manifest.json`: path to MCP server manifest JSON file.
- `--output-dir`: destination for generated YAML files (default: `contracts/`).
- One YAML file produced per tool in `manifest["tools"]`.
- Contract named `<server-name>.<tool-name>`.

### Programmatic

```python
from eva_mcp.importer import import_mcp_manifest, contracts_to_yaml

manifest = json.loads(Path("mcp-manifest.json").read_text())
contracts = import_mcp_manifest(manifest)
paths = contracts_to_yaml(contracts, output_dir=Path("contracts"))
```

### See Also

Full integration workflow: [A2A + MCP Integration Guide](a2a-mcp-guide.md).

---

## Plugin Authoring

Build custom evaluators and storage adapters as Eva plugins.

See: [Plugin Authoring Guide](plugin-authoring-guide.md).
