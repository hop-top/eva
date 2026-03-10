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

## Disabling Auth (Dev Mode)

Auth is implemented as a middleware factory. To disable in development:

```python
from server.app import create_app

app = create_app(middleware_factories=[])   # no auth middleware
```

Or simply: do not set `EVA_REDIS_URL`. Without Redis, the `_NullStateAdapter`
is used — it rejects all keys, effectively making every non-exempt request
return `401`. For true no-auth dev mode, pass `middleware_factories=[]`.

> Never disable auth in production.

---

## Behaviour Without Redis

When `EVA_REDIS_URL` is not set:

- `_NullStateAdapter` activates.
- All `X-Eva-Key` values rejected (`401 Invalid API key`).
- Exempt paths still served normally.

Set `EVA_REDIS_URL` before launching Eva to enable key validation.

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
- `middleware_factories=[]` only in dev/test — never in production.
