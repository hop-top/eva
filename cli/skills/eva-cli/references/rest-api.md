# Gateway REST API

Read when starting the gateway or calling it from another process.

```bash
eva serve --no-auth --host 127.0.0.1 --port 8080 --contracts-dir ./contracts
```

`--contracts-dir` loads every contract YAML in the folder; files that are not contracts are skipped with a warning. Without `--no-auth`, `eva serve` needs a key store (`EVA_REDIS_URL`) and every `/v1` call sends `X-Eva-Key: <key>`. `GET /health` needs no key.

## Routes

- `POST /v1/contract/evaluate`: score output you already hold against a named contract. Body `{"contract": "<name>", "output": "<string or object>", "prompt": "<optional>"}`. Calls nothing, stores nothing. An object `output` is serialised to JSON, so a `field:` evaluator reads its top-level key. The HTTP twin of `eva run --contract`.
- `POST /v1/contract/invoke`: the gateway forwards `body` to the contract's `provider` URL, evaluates the reply, retries per `retry_policy`. Body `{"contract": "<name>", "body": {...}}`.
- `POST /v1/proxy`: forward to any URL and evaluate inline. Body `{"target": "<url>", "body": {...}, "evaluators": [{"name": "contains", "mode": "binary", "config": {"substring": "refund"}}], "max_retries": 0}`.

## Status codes

- `200` with `eva_status: pass`.
- `422` with `eva_status: contract_violation` and a `violations` list (`evaluator`, `score`, `reason`): gate on this.
- `400` request invalid against `request_schema` (invoke only); `404` unknown contract; `401` missing or bad key; `502` upstream failure (proxy and invoke); `503` registry not initialised.
- A `skipped` list in the body names judge evaluators that did not run, and why.

Under `eva serve`, answered `invoke` (`source` `contract_invoke`) and `proxy` (`source` `gateway_proxy`) requests land in the same store as dataset runs: `.eva/state.db` in the directory serve was started from, or the file given with `eva serve --db <path>`. `evaluate` records nothing. Read them with `eva invocations show --id <uuid>` after finding the id in `eva failures list`, adding `--db <path>` if serve used it.
