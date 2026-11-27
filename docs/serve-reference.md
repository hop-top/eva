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
| `--no-auth` | `bool` | `false` | Serve without API-key authentication. Required when no key store (`EVA_REDIS_URL`) is configured; prints a warning at every start |
| `--help` | — | — | Show help and exit |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `EVA_REDIS_URL` | Redis connection URL — the API key store. Required unless `--no-auth` is passed |
| `EVA_NO_AUTH` | Set by `--no-auth` for worker and reload processes. Internal; do not set it yourself |
| `EVA_SERVE_CONTRACTS_DIR` | Set by `eva serve` for worker and reload processes (contracts directory). Internal; do not set it yourself |
| `EVA_CONTRACTS_DIR` | Overrides `--contracts-dir` (not natively wired; set via shell) |
| `EVA_STORAGE` | SQLite DB path for run storage (default: `sqlite:///.eva/state.db`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTEL collector endpoint (used by eva-otlp) |

> Note: Eva reads `EVA_REDIS_URL` at import time (`server/auth.py`). Set before
> launch; hot-reload does not re-read it.

---

## Startup Sequence

1. Parse CLI flags.
2. Check auth: no key store and no `--no-auth` prints an error naming both
   remedies on stderr and exits `2` before binding a port. With `--no-auth`,
   print a warning on stderr that the gateway is unauthenticated.
3. Construct `ContractRegistry`.
4. Scan `--contracts-dir` — load each `*.yaml` file as a `Contract`.
5. Log: `Loaded N contract(s) from <dir>` (or warning if dir missing).
6. Single process: call `create_app(registry=registry)` and hand the app to
   `uvicorn.run(...)`. With `--workers` > 1 or `--reload`, uvicorn needs an import
   string: it gets `server.app:create_serve_app` (a factory) and each worker or
   reload process builds its own app, loading contracts from the same directory.

> When `--reload` is set, `workers` is forced to `1` regardless of the flag value.

---

## Example Invocations

`--no-auth` below means: no API-key check on any route (a warning prints at
every start). Without it, `eva serve` needs `EVA_REDIS_URL` (see
[Security](security.md)).

### Dev mode (hot-reload)

```
eva serve --no-auth --reload --contracts-dir ./contracts
```

### Production (multiple workers, key store)

```
EVA_REDIS_URL=redis://redis:6379/0 \
  eva serve --host 0.0.0.0 --port 8080 --workers 4 --contracts-dir /etc/eva/contracts
```

### Sidecar (loopback only, single worker)

```
eva serve --no-auth --host 127.0.0.1 --port 9090 --contracts-dir ./contracts
```

### Minimal (no contracts, health-check only)

```
eva serve --no-auth
```

> Starts with an empty registry; `/v1/contract/invoke` returns 404 (unknown
> contract) until contracts are loaded. `/health` responds immediately.

---

## Notes

- Workers > 1 incompatible with `--reload`; reload silently wins.
- `--no-auth` wins even when `EVA_REDIS_URL` is set.
- No TLS termination — place behind a load balancer or reverse proxy for HTTPS.
- Auth requires `EVA_REDIS_URL`; without it `eva serve` exits `2` unless `--no-auth` is passed.
