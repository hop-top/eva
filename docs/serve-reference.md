# `eva serve` — Command Reference

Start the Eva gateway server.

---

## Synopsis

```
eva serve [OPTIONS]
```

---

## Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--host` | `str` | `0.0.0.0` | Bind address |
| `--port` | `int` | `8080` | Bind port |
| `--contracts-dir` | `path` | `contracts/` | Directory of contract YAML files to load |
| `--reload` | `bool` | `false` | Enable hot-reload (dev mode; forces `workers=1`) |
| `--workers` | `int` | `1` | Number of uvicorn worker processes |
| `--help` | — | — | Show help and exit |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `EVA_REDIS_URL` | Redis connection URL — enables API key auth |
| `EVA_CONTRACTS_DIR` | Overrides `--contracts-dir` (not natively wired; set via shell) |
| `EVA_STORAGE` | SQLite DB path for run storage (default: `sqlite:///.eva/state.db`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTEL collector endpoint (used by eva-otlp) |

> Note: Eva reads `EVA_REDIS_URL` at import time (`server/auth.py`). Set before
> launch; hot-reload does not re-read it.

---

## Startup Sequence

1. Parse CLI flags.
2. Construct `ContractRegistry`.
3. Scan `--contracts-dir` — load each `*.yaml` file as a `Contract`.
4. Log: `Loaded N contract(s) from <dir>` (or warning if dir missing).
5. Call `create_app(registry=registry)` — returns FastAPI app.
6. Hand off to `uvicorn.run(...)` with configured host/port/workers/reload.

> When `--reload` is set, `workers` is forced to `1` regardless of the flag value.

---

## Example Invocations

### Dev mode (hot-reload)

```
eva serve --reload --contracts-dir ./contracts
```

### Production (multiple workers)

```
eva serve --host 0.0.0.0 --port 8080 --workers 4 --contracts-dir /etc/eva/contracts
```

### Sidecar (loopback only, single worker)

```
eva serve --host 127.0.0.1 --port 9090 --contracts-dir ./contracts
```

### Minimal (no contracts, health-check only)

```
eva serve
```

> Starts with empty registry; returns 503 on `/v1/contract/invoke` until contracts
> are loaded. `/health` responds immediately.

---

## Notes

- Workers > 1 incompatible with `--reload`; reload silently wins.
- No TLS termination — place behind a load balancer or reverse proxy for HTTPS.
- Auth requires `EVA_REDIS_URL`; without it, all keys are rejected (null adapter).
