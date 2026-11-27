# Security Guide

---

## API Key Authentication

Eva authenticates requests via the `X-Eva-Key` header. Keys are stored in Redis
as simple existence flags; any key with a truthy value in Redis is valid.

### Key Storage Format

```
eva:apikey:<key>  →  "1"
```

Any truthy string value is accepted.

### Provisioning a Key

```sh
redis-cli SET "eva:apikey:eva_mykey_abc123" 1
```

Verify:

```sh
redis-cli GET "eva:apikey:eva_mykey_abc123"
# → "1"
```

Test the key:

```sh
curl -H "X-Eva-Key: eva_mykey_abc123" http://localhost:8080/v1/proxy \
  -d '{"target":"http://agent/","body":{}}'
```

### Key Rotation

1. Provision new key:
   ```sh
   redis-cli SET "eva:apikey:eva_newkey_xyz" 1
   ```
2. Update clients to use new key.
3. Delete old key:
   ```sh
   redis-cli DEL "eva:apikey:eva_oldkey_abc"
   ```

No restart required. Redis reads are per-request.

---

## Exempt Paths

The following paths bypass auth entirely:

| Path | Purpose |
|------|---------|
| `/health` | Liveness probe |
| `/.well-known/agent.json` | AGNTCY manifest (EE) |
| `/docs` | FastAPI Swagger UI |
| `/openapi.json` | OpenAPI schema |
| `/redoc` | ReDoc UI |

All other paths require a valid `X-Eva-Key`.

---

## Running Without Auth (`--no-auth`)

`eva serve` requires a key store. With no `EVA_REDIS_URL` set and no
`--no-auth`, it prints an error naming both remedies on stderr and exits with
code `2` without binding a port.

For local development, or when something in front of Eva authenticates callers,
pass `--no-auth`:

```sh
eva serve --no-auth
```

`--no-auth` serves every route without authentication and prints a warning on
stderr at every start. It wins even when `EVA_REDIS_URL` is set (Redis is also
used for other state). It applies in every mode: single process, `--workers`,
`--reload`. `--no-auth` sets `EVA_NO_AUTH` for the worker and reload processes
it spawns; that variable is internal, not a user-facing switch.

> `eva serve` binds `0.0.0.0` by default. Never use `--no-auth` on a network
> you do not control.

### Other ways to start the gateway

The refusal is a property of `eva serve`. Code that builds the app itself
behaves as before: `create_app()` and the module-level app
(`uvicorn server.app:app`) enforce auth only when `EVA_REDIS_URL` is set, and
serve every route unauthenticated otherwise. Passing
`middleware_factories=[]` does not disable auth when `EVA_REDIS_URL` is set.

---

## Behaviour Without Redis

When `EVA_REDIS_URL` is not set, no key store exists and no `X-Eva-Key` can be
validated. `eva serve` therefore refuses to start unless `--no-auth` is given
(see above); it never answers `401` for lack of a key store.

---

## EE Rate Limiting

Rate limiting is an Enterprise Edition feature. Requires `eva-ee`. Per-key
request rate caps enforced via Redis sliding windows.

See EE documentation for configuration details.

---

## HTTPS

Eva listens on plain HTTP. Do not expose Eva directly on a public network.

Terminate TLS at a load balancer or reverse proxy:

- **nginx** — `ssl_certificate` + `proxy_pass http://eva:8080`
- **Caddy** — automatic HTTPS with `reverse_proxy eva:8080`
- **Envoy / Istio** — mTLS sidecar mesh

Eva trusts the network between the proxy and itself; ensure that path is
firewalled or uses private networking.

---

## Summary Checklist

- `EVA_REDIS_URL` set and Redis reachable.
- At least one key provisioned before first request.
- Old keys deleted after rotation.
- `/health` and `/docs` locked down at proxy layer if needed.
- HTTPS terminated at load balancer.
- `--no-auth` only in dev/test or behind your own authentication — never exposed directly.
