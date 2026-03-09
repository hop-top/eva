# Dependency Trust Analysis
*Tool: rsx (quick mode, balanced policy) — 2026-03-09*

All deps pass balanced policy. Scores and risk flags below.

---

## Scores

| Dep | Repo | Score | Phase |
|---|---|---|---|
| rich | Textualize/rich | 7.5 | 1 |
| sqlmodel | tiangolo/sqlmodel | 7.3 | 1 |
| fastapi | tiangolo/fastapi | 7.3 | 3 |
| typer | tiangolo/typer | 7.2 | 1 |
| opentelemetry-sdk | open-telemetry/opentelemetry-python | 7.0 | 2 |
| redis-py | redis/redis-py | 6.9 | 2 |
| pydantic | pydantic/pydantic | 6.8 | 1 |
| sqlalchemy | sqlalchemy/sqlalchemy | 6.8 | 1 |
| pytest | pytest-dev/pytest | 6.8 | dev |
| litellm | BerriAI/litellm | 6.5 | 2 |
| httpx | encode/httpx | 6.4 | 3 |
| jsonschema | python-jsonschema/jsonschema | 6.4 | 1 |
| arq | samuelcolvin/arq | 5.9 | 3 |
| uvloop | MagicStack/uvloop | 5.8 | — |
| watchfiles | samuelcolvin/watchfiles | 5.7 | 3 |
| pluggy | pytest-dev/pluggy | 5.4 | 1 |
| agntcy-acp | agntcy/acp-sdk | 5.4 | 4 |

---

## Risk Flags + Mitigations

### litellm — score 6.5 ⚠️
- 1682 open issues, 36 open PRs — highest churn of all deps
- Fast-moving API surface; breaking changes between minors
- **Mitigation:** isolate behind `core/adapters/llm.py` ABC — swappable without
  touching evaluators. Pin to `>=1.x,<2` (minor-pinned). Integration tests
  mock `litellm.acompletion`; never call real API in CI.

### arq — score 5.9 ⚠️
- Activity 2.7/10 — maintainer pace is slow
- 103 open issues, 18 open PRs — backlog growing
- Maintenance 9.0 — code is fresh, just not actively extended
- **Mitigation:** isolate behind `server/queue/` — only Eva Server depends on it.
  Fallback candidates: `dramatiq`, `rq`. If arq stalls, swap is contained to
  one module. Pin to `>=0.27,<1`.

### watchfiles — score 5.7 ⚠️
- 0 open PRs — no community contribution signal
- Low activity; same author as arq (samuelcolvin)
- **Mitigation:** used only for contract registry hot-reload in `server/contracts/`.
  Can replace with 30s polling fallback (simpler, no dep) if watchfiles becomes
  a liability. Treat as optional — hot-reload is a convenience, not a contract.

### agntcy-acp — score 5.4 ⚠️
- Activity 1.0, adoption 1.0 — essentially prototype-tier (89 stars)
- Spec still evolving (v1.5.2 released but ecosystem immature)
- **Mitigation:** used only in `plugins/eva-agntcy/` — zero core dependency.
  If ACP spec breaks, only the plugin is affected. Pin to exact version
  `==1.5.2` until ecosystem stabilises. Reassess at Phase 4.

### pluggy — score 5.4 (misleading)
- Low adoption score (1.1) is a rsx blind spot — pluggy is pytest's own plugin
  system, used by millions of projects indirectly
- Activity 3.1 — intentionally slow; mature, stable API
- **No mitigation needed.** Score does not reflect true adoption. Treat as safe.

### uvloop — score 5.8 (dropped)
- Not listed as a dep in the plan — do not add
- Python 3.11+ asyncio is fast enough for Eva's I/O-bound workloads
- Low activity signal is moot; dep is unnecessary

---

## Summary Guidance for pyproject.toml

| Dep | Pin strategy |
|---|---|
| litellm | `>=1.0,<2` — minor-pin; monitor changelog |
| arq | `>=0.27,<1` — minor-pin |
| agntcy-acp | `==1.5.2` — exact-pin until spec stabilises |
| watchfiles | `>=0.21` — loose; optional in server extras |
| all others | `>=<current_major>` — standard lower-bound pin |

---

## rsx Audit Workflow (for future use)

Once draft `pyproject.toml` files exist per package:

```bash
rsx audit core/pyproject.toml --markdown
rsx audit server/pyproject.toml --markdown
rsx audit plugins/eva-agntcy/pyproject.toml --markdown
```

Output feeds directly into SBOM and dep trust report. Run on every new dep
addition before merging.
