# Deployment Guide

Running Eva Gateway in production.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EVA_REDIS_URL` | for auth | — | Redis URL, e.g. `redis://redis:6379/0` |
| `EVA_CONTRACTS_DIR` | no | `contracts/` | Path to contract YAML directory |
| `EVA_STORAGE` | no | `sqlite:///.eva/state.db` | Run storage DB URL |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | — | OTLP collector endpoint (eva-otlp) |
| `EVA_AGNTCY_REGISTRY_URL` | no | — | AGNTCY registry URL (EE only) |

---

## Docker

Minimal `Dockerfile` for `eva serve`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY contracts/ ./contracts/

EXPOSE 8080

CMD ["eva", "serve", "--host", "0.0.0.0", "--port", "8080",
     "--contracts-dir", "./contracts", "--workers", "2"]
```

Build and run:

```sh
docker build -t eva-gateway .
docker run -p 8080:8080 \
  -e EVA_REDIS_URL=redis://redis:6379/0 \
  -v $(pwd)/contracts:/app/contracts \
  eva-gateway
```

---

## Docker Compose

Eva + Redis stack:

```yaml
services:
  eva:
    image: eva-gateway:latest
    ports:
      - "8080:8080"
    environment:
      EVA_REDIS_URL: redis://redis:6379/0
      EVA_CONTRACTS_DIR: /etc/eva/contracts
    volumes:
      - ./contracts:/etc/eva/contracts:ro
    depends_on:
      redis:
        condition: service_healthy
    command: >
      eva serve
        --host 0.0.0.0
        --port 8080
        --contracts-dir /etc/eva/contracts
        --workers 2
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 5s

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
```

---

## Health Check Configuration

`GET /health` returns `200 {"status": "ok"}` when the process is alive.

- No auth required.
- No dependency checks (Redis, DB) — process liveness only.
- For readiness probes, add a custom check against `/v1/contract/invoke`
  or verify Redis connectivity externally.

---

## Production Checklist

- Auth enabled: `EVA_REDIS_URL` set; at least one key provisioned.
  See [Security Guide](security.md).
- Redis running and reachable before Eva starts.
- Contracts directory mounted read-only; populated with validated YAML.
  Run `eva contract validate <file>` before deploying.
- OTEL configured: `OTEL_EXPORTER_OTLP_ENDPOINT` set; `eva-otlp` installed.
  See [OTEL guide](otel.md).
- Workers: use `--workers N` where N = CPU count (no `--reload`).
- HTTPS terminated at load balancer or reverse proxy (nginx, Caddy, Envoy).
  Eva listens plain HTTP.
- Log level: set `LOG_LEVEL=info` (or `warning` in prod) via shell env.
- Contracts validated in CI: `eva contract validate` in pipeline.
- Rate limiting: EE feature — see EE docs.

---

## Package Index

Alpha packages distributed via private PyPI proxy.
Source: https://github.com/hop-top/eva-pkg

Partner install:

```sh
pip install eva \
  --index-url https://<token>@eva-pkg.ideacrafters-llc.workers.dev/simple/ \
  --extra-index-url https://pypi.org/simple/
```
