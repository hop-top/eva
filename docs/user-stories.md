# Eva — User Stories

All user stories grouped by persona. IDs are stable; append new stories at end of each group.

---

## Alex — AI Engineer

| ID     | Story |
|--------|-------|
| US-001 | As Alex, I want to scaffold a new Eva project with `eva init` so that I can start writing |
|        | evals without manual boilerplate. |
| US-002 | As Alex, I want to run a dataset of test cases against an LLM endpoint with `eva run` so |
|        | that I can verify my prompt changes don't regress. |
| US-003 | As Alex, I want `eva run` to exit non-zero when any eval fails so that CI blocks the merge |
|        | automatically. |
| US-004 | As Alex, I want to validate a contract YAML with `eva contract validate` so that I catch |
|        | schema errors before committing. |
| US-005 | As Alex, I want to diff two contract versions with `eva contract diff` so that I can see |
|        | breaking changes introduced by a prompt update. |

---

## Sam — Platform Engineer

| ID     | Story |
|--------|-------|
| US-006 | As Sam, I want to start an Eva gateway with `eva serve` so that all LLM traffic passes |
|        | through a validated proxy layer. |
| US-007 | As Sam, I want Eva to expose a `/health` endpoint so that my load-balancer can detect |
|        | outages and route around them. |
| US-008 | As Sam, I want the proxy to retry failed requests with injected hints so that transient |
|        | LLM quality failures are recovered without client involvement. |
| US-009 | As Sam, I want to configure auth token requirements on the gateway so that only authorised |
|        | callers can invoke LLM endpoints through Eva. |
| US-010 | As Sam, I want per-request evaluator configuration on the `/v1/proxy` endpoint so that |
|        | each integration can enforce its own quality contract at runtime. |

---

## Jordan — Compliance Officer

| ID     | Story |
|--------|-------|
| US-011 | As Jordan, I want to generate a drift report with `eva drift report` so that I can document |
|        | when model behaviour deviates from the approved baseline. |
| US-012 | As Jordan, I want drift reports to be stored in a persistent DB so that I have a historical |
|        | record for audits. |
| US-013 | As Jordan, I want Eva to emit OpenTelemetry traces for every eval run so that my SIEM can |
|        | ingest and alert on quality regressions. |
| US-014 | As Jordan, I want contract YAML files to be version-controlled and diffable so that every |
|        | change to an approved output contract is trackable. |
| US-015 | As Jordan, I want `eva drift report` to exit non-zero when no baseline runs exist so that |
|        | missing-data gaps are surfaced rather than silently ignored. |

---

## Taylor — OSS Contributor / Plugin Author

| ID     | Story |
|--------|-------|
| US-016 | As Taylor, I want to implement a custom evaluator by subclassing `EvaPlugin` so that I can |
|        | encode domain-specific quality rules without forking Eva. |
| US-017 | As Taylor, I want to register my plugin via a `pyproject.toml` entry point so that it is |
|        | auto-discovered when installed alongside Eva. |
| US-018 | As Taylor, I want to drop an `eva_plugins.py` file in the project root so that local |
|        | one-off evaluators are loaded without packaging overhead. |
| US-019 | As Taylor, I want the `run_eval` hook to receive the full response and context dict so that |
|        | my evaluator can make fine-grained decisions based on test metadata. |
| US-020 | As Taylor, I want plugin errors to be isolated and reported as a failed score rather than |
|        | crashing the runner so that one bad plugin doesn't abort the whole suite. |

---

## Coverage Matrix

| US ID  | Persona | Primary CLI / API          | E2E Test File                  |
|--------|---------|----------------------------|-------------------------------|
| US-001 | Alex    | `eva init`                 | test_init.py                  |
| US-002 | Alex    | `eva run`                  | test_run.py                   |
| US-003 | Alex    | `eva run` exit code        | test_run.py                   |
| US-004 | Alex    | `eva contract validate`    | test_contract_validate.py     |
| US-005 | Alex    | `eva contract diff`        | test_contract_diff.py         |
| US-006 | Sam     | `eva serve`                | test_serve_command.py         |
| US-007 | Sam     | `/health`                  | test_serve_command.py         |
| US-008 | Sam     | `/v1/proxy` retry          | test_server_e2e.py            |
| US-009 | Sam     | gateway auth               | test_serve_command.py         |
| US-010 | Sam     | `/v1/proxy` evaluators     | test_server_e2e.py            |
| US-011 | Jordan  | `eva drift report`         | test_drift_command.py         |
| US-012 | Jordan  | drift DB persistence       | test_drift_command.py         |
| US-013 | Jordan  | OTEL traces                | (integration; future)         |
| US-014 | Jordan  | `eva contract diff`        | test_contract_diff.py         |
| US-015 | Jordan  | `eva drift report` exit 1  | test_drift_command.py         |
| US-016 | Taylor  | plugin SDK / `eva run`     | test_plugin_e2e.py            |
| US-017 | Taylor  | entry_points discovery     | (unit; future)                |
| US-018 | Taylor  | `eva_plugins.py` local     | test_plugin_e2e.py            |
| US-019 | Taylor  | `run_eval` hook context    | test_plugin_e2e.py            |
| US-020 | Taylor  | plugin error isolation     | test_plugin_e2e.py            |
