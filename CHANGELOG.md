# Changelog

All notable changes to Eva are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [PEP 440](https://peps.python.org/pep-0440/)

## [0.1.0-alpha.2](https://github.com/hop-top/eva/compare/eva/v0.1.0-alpha.1...eva/v0.1.0-alpha.2) (2026-08-20)


### Features

* **action:** add reusable GitHub Action for CI/CD contract evaluation ([1d63240](https://github.com/hop-top/eva/commit/1d63240c30a1366ab489548d939c22040d859af4))
* **cli:** eva contract validate ([831edb6](https://github.com/hop-top/eva/commit/831edb6b453759b903ddbf11e2503c885fcf71a5))
* **cli:** eva init — scaffold project structure ([097e587](https://github.com/hop-top/eva/commit/097e587242f1e3201929038acacd0bf0b0563085))
* **cli:** eva run — end-to-end evaluation flow ([ec811c5](https://github.com/hop-top/eva/commit/ec811c58701568f9a51ce046d2274b5690cb5d37))
* **cli:** eva serve command — starts FastAPI gateway with contract registry ([6fec0a9](https://github.com/hop-top/eva/commit/6fec0a901043851848fd702b86f847844e8e6fbb))
* **cli:** T-0031/T-0032 — rich TUI progress + JSONL e2e + --no-tui + --target validation ([8e9df16](https://github.com/hop-top/eva/commit/8e9df164d2f1cf978a9983e897160d472e70806b))
* **cli:** T-0033 — eva contract diff command ([11f851b](https://github.com/hop-top/eva/commit/11f851bcb2910fbb007c4d6da68b6a02bf7a71fc))
* **core,cli:** T-0056 — drift detection engine + eva drift report command ([12fc2d2](https://github.com/hop-top/eva/commit/12fc2d2ffc9cb3917e34f3996b495b66c12055ff))
* **core:** async runner with semaphore concurrency ([4c6e245](https://github.com/hop-top/eva/commit/4c6e245ef1858a2f9198750cec5c3d3544e125cd))
* **core:** contract YAML loader with validation ([f2c420b](https://github.com/hop-top/eva/commit/f2c420bf8824720678a508eda9d9d25332558c12))
* **core:** dataset loader — YAML and JSONL formats ([d2f13ac](https://github.com/hop-top/eva/commit/d2f13ac91639329f917d7cafa84d0817881867ab))
* **core:** deterministic evaluators — contains, regex, json_schema, no_pii ([a9ceba7](https://github.com/hop-top/eva/commit/a9ceba737a6c8cdd10cc571fb0033be1778e2630))
* **core:** Phase 2 adapter layer — config, ABCs, storage, state, otel ([99e0ae9](https://github.com/hop-top/eva/commit/99e0ae91a8daa5730abb3e4625791d3b13d0d332))
* **core:** pluggy hook system — before_eval, run_eval, after_eval ([1ff07b9](https://github.com/hop-top/eva/commit/1ff07b98ffd76a654d1e2ab0b6172a7efb63a784))
* **core:** plugin loader — file-based and entry_points ([9b3ade8](https://github.com/hop-top/eva/commit/9b3ade89c5640a291c6ccc20a99b03f4748342b9))
* **core:** SQLite storage adapter via SQLModel ([ddfae5c](https://github.com/hop-top/eva/commit/ddfae5c8d2e271fc931449ab2709d7c78bcbcfc7))
* **ee:** T-0054 — sliding window rate limiting per API key (Redis-backed) ([3f06d2d](https://github.com/hop-top/eva/commit/3f06d2d1482aa59aa1f871c2390f3af35c448560))
* **evaluators:** P1+P2 expansion — 25 evaluators + registry sweep + prose-assertion mode override ([#2](https://github.com/hop-top/eva/issues/2)) ([b825776](https://github.com/hop-top/eva/commit/b825776aadea972ce6c481fee99787980d469c5a))
* **evaluators:** wire builtins + LLM judges into dataset mode ([5c021d8](https://github.com/hop-top/eva/commit/5c021d81ec2e254aa3a39cf7239853af5ca650da))
* **plugins:** eva-a2a — A2A Agent Card JSON to Eva contract YAML importer ([20f2075](https://github.com/hop-top/eva/commit/20f20757000cf1f9ae291f6ed57611bb9c01fd7a))
* **plugins:** eva-agntcy — ACP manifest endpoint + OASF local registry ([77d5143](https://github.com/hop-top/eva/commit/77d5143a4c3cd3a13ae6507e43cb495de37d50f7))
* **plugins:** eva-mcp — MCP server manifest JSON to Eva contract YAML importer ([b61c066](https://github.com/hop-top/eva/commit/b61c06660551db80fd714eef3c663e2b5170a809))
* **plugins:** eva-otlp — OTLP trace exporter wrapping opentelemetry-sdk ([c28a7ac](https://github.com/hop-top/eva/commit/c28a7acb0964c3969c3d8f20b08cbd9c7af592f1))
* **plugins:** eva-postgres — PostgreSQL storage adapter via SQLModel ([3347a5c](https://github.com/hop-top/eva/commit/3347a5c993f671d5628d599a3c02315abfeb90e6))
* **runner:** concurrency modes, otel adapter, evaluator config wiring ([523927f](https://github.com/hop-top/eva/commit/523927f240b496c5d5bc1ba38a56b22796564947))
* **server:** ARQ async eval task + worker settings (requires Redis for production use) ([26331ab](https://github.com/hop-top/eva/commit/26331aba712c413d78d7b4b1cba377d08a8c245f))
* **server:** async HTTP proxy forwarder ([805dd31](https://github.com/hop-top/eva/commit/805dd31d6152e5a367720ffd1556e4e8f275ba02))
* **server:** contract registry — load, reload, directory scan ([0ce237e](https://github.com/hop-top/eva/commit/0ce237e64c94e00082f554d138b1180f584e971e))
* **server:** contract registry hot-reload via watchfiles ([32f6710](https://github.com/hop-top/eva/commit/32f67108938313da641eb795aa25717c51741362))
* **server:** FastAPI app scaffold with /health endpoint ([6dd7811](https://github.com/hop-top/eva/commit/6dd78118448d3c9902d681c2b613e12a42f30a9f))
* **server:** inline response evaluator — runs contract evaluators, returns violations ([1f0fec1](https://github.com/hop-top/eva/commit/1f0fec1daddf193c46af9aac5cee640e97e1d592))
* **server:** OTEL span instrumentation — noop fallback when opentelemetry not installed ([d3a5d30](https://github.com/hop-top/eva/commit/d3a5d30d1e03584f3143832140002b8a3f986b25))
* **server:** POST /v1/proxy — forward, evaluate, retry, structured response ([3d7ca6b](https://github.com/hop-top/eva/commit/3d7ca6b4b732cee41b7bbfc0008bee1aacb64fd8))
* **server:** request body JSON Schema validation ([7d80c28](https://github.com/hop-top/eva/commit/7d80c284de04e15923287197e5ebff2d60c8771c))
* **server:** retry engine — hint injection, backoff, RetryExhausted on max attempts ([fd481a6](https://github.com/hop-top/eva/commit/fd481a622f4cd64746f1c330e22709986ef2fe08))
* **server:** T-0053 — ApiKeyMiddleware with X-Eva-Key header auth ([c2bd0c8](https://github.com/hop-top/eva/commit/c2bd0c825b0bad90b1ed196303a03f5f7308951c))
* **server:** T-0090 — extend create_app() with middleware_factories hook ([6c8336a](https://github.com/hop-top/eva/commit/6c8336adc22095eb22e55478e9c486ceee275e7b))


### Bug Fixes

* **cli:** version from package metadata ([abfa241](https://github.com/hop-top/eva/commit/abfa241369a163fe2f27b1f0a99a5427d04819bf))
* merge Phase 2 branches — resolve pyproject conflicts, fix runner.concurrency attr, add litellm dep ([261f4b4](https://github.com/hop-top/eva/commit/261f4b4711d1339929e3aded803b6fb34029ebbb))
* **plans:** Phase 1 — conftest, markers, entry-points, dep strategy, test layout ([f436d3b](https://github.com/hop-top/eva/commit/f436d3ba5693069bcfea0debd807f6403ba7f245))
* **plans:** Phase 2 — conftest fixtures, parametrize evaluators, marker declarations ([121cd59](https://github.com/hop-top/eva/commit/121cd59a626a9a8ea5c3691d580d5eaf93c647e0))
* **plans:** Phase 3 — pytest markers, py.typed for server, entry-point note ([8003757](https://github.com/hop-top/eva/commit/800375771ed4b387a812c7a394805be5448dc350))
* **plans:** Phase 4 — conftest upgrade, strict-markers for smoke tests ([2e64937](https://github.com/hop-top/eva/commit/2e64937f7cd9f3a8550e79c21f2349386720ba0b))
* **server:** gateway version from package metadata ([e635e66](https://github.com/hop-top/eva/commit/e635e665de202d6fa3e7c547d7277d1196a32a9d))


### Documentation

* A2A + MCP integration guide ([7e9cc3a](https://github.com/hop-top/eva/commit/7e9cc3a07fe7d378af64822053c017a25b8f3bf1))
* **action:** GitHub Action usage guide ([a4c00dd](https://github.com/hop-top/eva/commit/a4c00dd4a5c6f1fc679e68384263f5e9e2f2ad8b))
* **agents:** repos, paths, cloud service, phases 1-5 complete ([f293442](https://github.com/hop-top/eva/commit/f2934420291c6a7034b624eeffe8578fc4890782))
* **contrib:** CONTRIBUTING.md + .gitmodules stub + submodule setup guide ([8dca83c](https://github.com/hop-top/eva/commit/8dca83cdffa21ecaaa4f28bc9a6e4f9f8c03eb67))
* dependency trust analysis via rsx — scores, risks, mitigations ([7963dcc](https://github.com/hop-top/eva/commit/7963dcc95eff9aa09d35c2012d197fb6e2196655))
* deployment guide — Docker, Compose, env vars, production checklist ([91a7aad](https://github.com/hop-top/eva/commit/91a7aad05dbde35aff0301efddb84be3a017ad6c))
* drift detection guide — eva drift report command and use cases ([8328eb8](https://github.com/hop-top/eva/commit/8328eb8802a2fa52b05412ebeb6ab269fd6bb68b))
* **ee:** EE repo init procedure + ee/ placeholder ([ce7eebf](https://github.com/hop-top/eva/commit/ce7eebf3bd6281d523b439371fc7cdf0cddc3a2a))
* eva serve command reference ([65ccb06](https://github.com/hop-top/eva/commit/65ccb06f5ead541978d27a7a6d166438da62aeb8))
* Gateway API reference ([6fb6699](https://github.com/hop-top/eva/commit/6fb6699d313e1faab93ad27209ea74c05ac19c34))
* move domain evaluators to ecosystem, out of Phase 4 scope ([d188f95](https://github.com/hop-top/eva/commit/d188f95dbc330a1458e4a743ef9eae619c71258b))
* official plugins guide — eva-postgres, eva-otlp, eva-a2a, eva-mcp ([79eb619](https://github.com/hop-top/eva/commit/79eb61987f650071cae850dc44230522ad64dcd9))
* **personas:** define 4 personas + user stories (US-001–US-020) ([d384cda](https://github.com/hop-top/eva/commit/d384cda72276bec2c0f672b6ef968c068c17896e))
* Phase 1 core foundation technical documentation and user manual ([aa458ca](https://github.com/hop-top/eva/commit/aa458cafc2345006c79a0fa4911dd82fd7e68de6))
* Phase 1 implementation plan — Core Foundation ([f30f78b](https://github.com/hop-top/eva/commit/f30f78b4d9d8b68e1c2e53eb2573c478569210ca))
* Phase 2 implementation plan — Core Power ([2c88b5b](https://github.com/hop-top/eva/commit/2c88b5b791423a3df5e4102c301bbf0cbe079c2b))
* Phase 3 implementation plan — Server and Plugins ([db150cd](https://github.com/hop-top/eva/commit/db150cd3c57c20768bb42647c91d671311dad0fd))
* Phase 4 implementation plan — Hardening and Ecosystem Plugins ([7717de7](https://github.com/hop-top/eva/commit/7717de75b71763ef1f4e081f6c747be42a0ac986))
* **phase4:** CE/EE split — label tasks, add middleware hook task, update plan ([55419b6](https://github.com/hop-top/eva/commit/55419b6c3a506ab0812dd45b2e6633a2b59c0e98))
* **phase5:** packaging + pre-release plan — alpha/beta gates, dual licensing, R2 private PyPI ([2f4271c](https://github.com/hop-top/eva/commit/2f4271ce44c51507aab9885160a3d31c4a432d39))
* **plan:** eva invite command — invite codes, share, signup, worker endpoints ([07005fa](https://github.com/hop-top/eva/commit/07005fabc0cc74078f0cd893731caee17a0a9a00))
* **release:** add CHANGELOG — 0.1.0a1 covering phases 1–4 ([b8ec200](https://github.com/hop-top/eva/commit/b8ec200ab645fec7b71b5ce739a0ae8376bf0740))
* **release:** add README — quickstart, concepts, badges ([93223ee](https://github.com/hop-top/eva/commit/93223eeb8fa0e9e40177396d11a54ba08189b5b5))
* **release:** alpha GitHub release runbook ([9eade0e](https://github.com/hop-top/eva/commit/9eade0e84e8405dafbdc0ddc8f16b6d85c8e2836))
* replace initial plan with validated architecture design ([968c4c2](https://github.com/hop-top/eva/commit/968c4c2d955999c5d102eb189e9c4f57454cd466))
* retry and self-healing reference ([b60c9d2](https://github.com/hop-top/eva/commit/b60c9d2530d6c12d7d1b596374fba37fe3d70e20))
* security guide — API keys, rotation, exempt paths, HTTPS ([9dea0a5](https://github.com/hop-top/eva/commit/9dea0a5cbc287b6c706c328e97f1f7d11348f001))
* T-0059–T-0063 — Phase 2 doc set ([f8b897c](https://github.com/hop-top/eva/commit/f8b897c2d3cc0864a45184ad70c412dcac945cc0))
* update private PyPI refs to eva-pkg worker URL ([758afdd](https://github.com/hop-top/eva/commit/758afdd0c5dbc4186f5d3b7ce4a935bdfcbff57d))

## [Unreleased]

## [0.1.0a1] - 2026-03-09

### Added — Phase 1: Core Foundation
- Contract YAML spec + loader
- Evaluators: `contains`, `regex_match`, `json_schema_valid`, `no_pii`
- CLI: `eva init`, `eva run`, `eva contract validate`, `eva contract diff`
- SQLite storage adapter, OTEL adapter stubs
- Plugin system via pluggy

### Added — Phase 2: Core Power
- LLM-as-judge evaluator (litellm backend)
- Concurrency modes: async, sync, threaded
- Redis state adapter
- OTEL exporter adapter
- `eva contract diff` rich TUI output

### Added — Phase 3: Server + Plugins
- FastAPI gateway: `eva serve`, `POST /v1/proxy`, `POST /v1/contract/invoke`
- Contract registry + hot-reload (watchfiles)
- Request schema validation middleware
- Retry + self-healing engine with hint injection
- ARQ async evaluation queue
- Official plugins: `eva-postgres`, `eva-otlp`, `eva-a2a`, `eva-mcp`

### Added — Phase 4: Hardening
- API key authentication middleware (`X-Eva-Key`)
- Drift detection: `eva drift report` CLI
- EE: rate limiting (sliding window, Redis)
- EE: webhook emission on violations
- EE: `eva-agntcy` plugin (ACP manifest, `/.well-known/agent.json`)

[0.1.0a1]: https://github.com/hop-top/eva/releases/tag/v0.1.0a1
