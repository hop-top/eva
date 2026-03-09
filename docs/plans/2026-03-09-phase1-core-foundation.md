# Phase 1: Eva Core Foundation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A developer can install Eva, define a contract, run evaluations locally, and gate CI — all from the command line.

**Architecture:** Monorepo with three top-level packages (`cli/`, `core/`, `server/`). Phase 1 only touches `core/` and `cli/`. The `core/` package defines all models, interfaces, and evaluators. The `cli/` package is a thin Typer app that calls into `core/`. Tests are E2E via subprocess — they run the actual CLI and assert stdout and exit codes.

**Tech Stack:** Python 3.11+, Typer, rich, pluggy, SQLModel, PyYAML, jsonschema, pytest, uv (package manager)

---

## Project Setup

### Task 1: Repository structure + packaging

**Files:**
- Create: `pyproject.toml`
- Create: `core/__init__.py`
- Create: `core/py.typed`
- Create: `cli/__init__.py`
- Create: `cli/main.py`
- Create: `tests/__init__.py`
- Create: `tests/e2e/__init__.py`
- Create: `.env.example`
- Create: `.gitignore`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "eva"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "rich>=13",
    "pluggy>=1.4",
    "sqlmodel>=0.0.21",
    "pyyaml>=6",
    "jsonschema>=4.23",
    "python-dotenv>=1",
]

[project.scripts]
eva = "cli.main:app"

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 2: Create minimal package files**

```python
# core/__init__.py
# core/py.typed  (empty — marks package as typed)
# cli/__init__.py
# tests/__init__.py
# tests/e2e/__init__.py
```

```python
# cli/main.py
import typer
app = typer.Typer()

if __name__ == "__main__":
    app()
```

**Step 3: Install in dev mode**

```bash
uv pip install -e ".[dev]"
```

Expected: no errors. `eva --help` shows empty Typer app.

**Step 4: Commit**

```bash
git add pyproject.toml core/ cli/ tests/ .env.example .gitignore
git commit -m "chore: project scaffold — Eva Core Phase 1"
```

---

## Task 2: Core data models

**Files:**
- Create: `core/models.py`
- Create: `tests/unit/test_models.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_models.py
from datetime import datetime
from core.models import Score, Result, Contract, RetryPolicy, Run, EvaluatorRef

def test_score_value_range():
    s = Score(value=0.5)
    assert 0.0 <= s.value <= 1.0

def test_score_defaults():
    s = Score(value=1.0)
    assert s.reason is None
    assert s.metadata == {}

def test_result_binary_pass():
    r = Result(
        test_id="t1", evaluator="contains", score=Score(value=1.0),
        mode="binary", duration_ms=10, trace_id=None
    )
    assert r.passed is True

def test_result_binary_fail():
    r = Result(
        test_id="t1", evaluator="contains", score=Score(value=0.0),
        mode="binary", duration_ms=10, trace_id=None
    )
    assert r.passed is False

def test_result_threshold_pass():
    r = Result(
        test_id="t1", evaluator="quality", score=Score(value=0.8),
        mode="threshold", min_score=0.7, duration_ms=10, trace_id=None
    )
    assert r.passed is True

def test_result_threshold_fail():
    r = Result(
        test_id="t1", evaluator="quality", score=Score(value=0.5),
        mode="threshold", min_score=0.7, duration_ms=10, trace_id=None
    )
    assert r.passed is False

def test_result_warn_always_passes():
    r = Result(
        test_id="t1", evaluator="tone", score=Score(value=0.0),
        mode="warn", duration_ms=10, trace_id=None
    )
    assert r.passed is True

def test_retry_policy_defaults():
    rp = RetryPolicy()
    assert rp.max_retries == 2
    assert rp.hint is None
    assert rp.backoff_ms == 0

def test_contract_minimal():
    c = Contract(
        name="refund_policy",
        provider="billing-agent",
        request_schema={"type": "object"},
        evaluators=[],
        retry_policy=RetryPolicy()
    )
    assert c.consumer is None
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.models'`

**Step 3: Implement models**

```python
# core/models.py
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, model_validator


class Score(BaseModel):
    value: float
    reason: str | None = None
    metadata: dict = {}


class EvaluatorRef(BaseModel):
    name: str
    mode: Literal["binary", "threshold", "warn"] = "binary"
    min_score: float = 1.0


class RetryPolicy(BaseModel):
    max_retries: int = 2
    hint: str | None = None
    backoff_ms: int = 0


class Contract(BaseModel):
    name: str
    provider: str
    consumer: str | None = None
    request_schema: dict = {}
    evaluators: list[EvaluatorRef] = []
    retry_policy: RetryPolicy = RetryPolicy()


class Result(BaseModel):
    test_id: str
    evaluator: str
    score: Score
    mode: Literal["binary", "threshold", "warn"]
    min_score: float = 1.0
    passed: bool = False
    duration_ms: int
    trace_id: str | None = None

    @model_validator(mode="after")
    def compute_passed(self) -> "Result":
        if self.mode == "binary":
            self.passed = self.score.value == 1.0
        elif self.mode == "threshold":
            self.passed = self.score.value >= self.min_score
        elif self.mode == "warn":
            self.passed = True
        return self


class Run(BaseModel):
    run_id: str
    dataset: str
    target: str
    results: list[Result] = []
    started_at: datetime
    duration_ms: int = 0
    passed: bool = False
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_models.py -v
```

Expected: all tests PASS.

**Step 5: Commit**

```bash
git add core/models.py tests/unit/
git commit -m "feat(core): data models — Score, Result, Contract, Run"
```

---

## Task 3: Contract YAML loader

**Files:**
- Create: `core/contract.py`
- Create: `tests/unit/test_contract.py`
- Create: `tests/fixtures/contracts/valid.yaml`
- Create: `tests/fixtures/contracts/invalid_missing_name.yaml`

**Step 1: Create fixture contracts**

```yaml
# tests/fixtures/contracts/valid.yaml
name: refund_policy
provider: billing-agent
consumer: support-agent
request_schema:
  type: object
  required: [order_id]
  properties:
    order_id:
      type: string
evaluators:
  - name: json_schema_valid
    mode: binary
  - name: no_discount_violation
    mode: binary
retry_policy:
  max_retries: 3
  hint: "Ensure response is valid JSON and discount is <= 20%"
```

```yaml
# tests/fixtures/contracts/invalid_missing_name.yaml
provider: billing-agent
evaluators: []
```

**Step 2: Write failing tests**

```python
# tests/unit/test_contract.py
import pytest
from pathlib import Path
from core.contract import load_contract, ContractValidationError

FIXTURES = Path("tests/fixtures/contracts")

def test_load_valid_contract():
    c = load_contract(FIXTURES / "valid.yaml")
    assert c.name == "refund_policy"
    assert c.provider == "billing-agent"
    assert c.consumer == "support-agent"
    assert len(c.evaluators) == 2
    assert c.retry_policy.max_retries == 3

def test_load_sets_defaults():
    c = load_contract(FIXTURES / "valid.yaml")
    assert c.retry_policy.backoff_ms == 0

def test_load_missing_name_raises():
    with pytest.raises(ContractValidationError, match="name"):
        load_contract(FIXTURES / "invalid_missing_name.yaml")

def test_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_contract(Path("does/not/exist.yaml"))
```

**Step 3: Run tests to verify they fail**

```bash
pytest tests/unit/test_contract.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.contract'`

**Step 4: Implement contract loader**

```python
# core/contract.py
from pathlib import Path
import yaml
from pydantic import ValidationError
from core.models import Contract


class ContractValidationError(Exception):
    pass


def load_contract(path: Path) -> Contract:
    if not path.exists():
        raise FileNotFoundError(f"Contract file not found: {path}")
    raw = yaml.safe_load(path.read_text())
    if not raw or "name" not in raw:
        raise ContractValidationError("Contract must have a 'name' field")
    try:
        return Contract.model_validate(raw)
    except ValidationError as e:
        raise ContractValidationError(str(e)) from e
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_contract.py -v
```

Expected: all PASS.

**Step 6: Commit**

```bash
git add core/contract.py tests/unit/test_contract.py tests/fixtures/
git commit -m "feat(core): contract YAML loader with validation"
```

---

## Task 4: Evaluator interface + pluggy hook system

**Files:**
- Create: `core/plugins.py`
- Create: `tests/unit/test_plugins.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_plugins.py
from core.plugins import EvaSpec, EvaPlugin, make_manager
from core.models import Score


class PassEvaluator(EvaPlugin):
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(value=1.0)


class FailEvaluator(EvaPlugin):
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(value=0.0, reason="always fails")


def test_hook_manager_runs_evaluator():
    pm = make_manager()
    pm.register(PassEvaluator())
    results = pm.hook.run_eval(response="hello", context={})
    assert len(results) == 1
    assert results[0].value == 1.0


def test_multiple_evaluators_run():
    pm = make_manager()
    pm.register(PassEvaluator())
    pm.register(FailEvaluator())
    results = pm.hook.run_eval(response="hello", context={})
    assert len(results) == 2


def test_before_after_hooks_called():
    called = []

    class TracingEvaluator(EvaPlugin):
        @EvaSpec.hook_impl
        def before_eval(self, test_id: str, context: dict) -> None:
            called.append(f"before:{test_id}")

        @EvaSpec.hook_impl
        def run_eval(self, response: str, context: dict) -> Score:
            return Score(value=1.0)

        @EvaSpec.hook_impl
        def after_eval(self, test_id: str, score: Score, context: dict) -> None:
            called.append(f"after:{test_id}")

    pm = make_manager()
    pm.register(TracingEvaluator())
    pm.hook.before_eval(test_id="t1", context={})
    pm.hook.run_eval(response="hi", context={})
    pm.hook.after_eval(test_id="t1", score=Score(value=1.0), context={})
    assert called == ["before:t1", "after:t1"]
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_plugins.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.plugins'`

**Step 3: Implement pluggy hook system**

```python
# core/plugins.py
import pluggy
from core.models import Score

hookspec = pluggy.HookspecMarker("eva")
hookimpl = pluggy.HookimplMarker("eva")


class EvaSpec:
    hook_impl = staticmethod(hookimpl)

    @hookspec
    def before_eval(self, test_id: str, context: dict) -> None:
        """Called before running an evaluator."""

    @hookspec
    def run_eval(self, response: str, context: dict) -> Score:
        """Run an evaluator. Returns a Score."""

    @hookspec
    def after_eval(self, test_id: str, score: Score, context: dict) -> None:
        """Called after running an evaluator."""


class EvaPlugin:
    """Base class for Eva evaluator plugins."""
    pass


def make_manager() -> pluggy.PluginManager:
    pm = pluggy.PluginManager("eva")
    pm.add_hookspecs(EvaSpec)
    return pm
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_plugins.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add core/plugins.py tests/unit/test_plugins.py
git commit -m "feat(core): pluggy hook system — before_eval, run_eval, after_eval"
```

---

## Task 5: Built-in deterministic evaluators (Tier 1)

**Files:**
- Create: `core/evaluators/contains.py`
- Create: `core/evaluators/regex_match.py`
- Create: `core/evaluators/json_schema_valid.py`
- Create: `core/evaluators/no_pii.py`
- Create: `core/evaluators/__init__.py`
- Create: `tests/unit/test_evaluators.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_evaluators.py
import pytest
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.no_pii import NoPiiEvaluator


# --- contains ---
def test_contains_pass():
    e = ContainsEvaluator(substring="refund")
    score = e._run("Your refund has been processed")
    assert score.value == 1.0

def test_contains_fail():
    e = ContainsEvaluator(substring="refund")
    score = e._run("Sorry, we cannot help")
    assert score.value == 0.0
    assert "refund" in score.reason

def test_contains_case_insensitive():
    e = ContainsEvaluator(substring="refund", case_sensitive=False)
    score = e._run("Your REFUND is ready")
    assert score.value == 1.0


# --- regex ---
def test_regex_pass():
    e = RegexEvaluator(pattern=r"\d{3}-\d{4}")
    score = e._run("Call 555-1234 for help")
    assert score.value == 1.0

def test_regex_fail():
    e = RegexEvaluator(pattern=r"\d{3}-\d{4}")
    score = e._run("No phone number here")
    assert score.value == 0.0


# --- json_schema_valid ---
def test_json_schema_valid_pass():
    e = JsonSchemaEvaluator(schema={"type": "object", "required": ["price"]})
    score = e._run('{"price": 42}')
    assert score.value == 1.0

def test_json_schema_valid_fail_not_json():
    e = JsonSchemaEvaluator(schema={"type": "object"})
    score = e._run("not json at all")
    assert score.value == 0.0
    assert score.reason is not None

def test_json_schema_valid_fail_schema():
    e = JsonSchemaEvaluator(schema={"type": "object", "required": ["price"]})
    score = e._run('{"discount": 10}')
    assert score.value == 0.0


# --- no_pii ---
def test_no_pii_pass():
    e = NoPiiEvaluator()
    score = e._run("Your order has been processed successfully")
    assert score.value == 1.0

def test_no_pii_fail_email():
    e = NoPiiEvaluator()
    score = e._run("Contact john@example.com for help")
    assert score.value == 0.0
    assert score.reason is not None

def test_no_pii_fail_ssn():
    e = NoPiiEvaluator()
    score = e._run("SSN: 123-45-6789")
    assert score.value == 0.0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_evaluators.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: Implement evaluators**

```python
# core/evaluators/__init__.py
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.no_pii import NoPiiEvaluator

__all__ = ["ContainsEvaluator", "RegexEvaluator", "JsonSchemaEvaluator", "NoPiiEvaluator"]
```

```python
# core/evaluators/contains.py
from core.models import Score


class ContainsEvaluator:
    def __init__(self, substring: str, case_sensitive: bool = True):
        self.substring = substring
        self.case_sensitive = case_sensitive

    def _run(self, response: str) -> Score:
        haystack = response if self.case_sensitive else response.lower()
        needle = self.substring if self.case_sensitive else self.substring.lower()
        if needle in haystack:
            return Score(value=1.0)
        return Score(value=0.0, reason=f"Response does not contain '{self.substring}'")
```

```python
# core/evaluators/regex_match.py
import re
from core.models import Score


class RegexEvaluator:
    def __init__(self, pattern: str):
        self.pattern = re.compile(pattern)

    def _run(self, response: str) -> Score:
        if self.pattern.search(response):
            return Score(value=1.0)
        return Score(value=0.0, reason=f"Pattern '{self.pattern.pattern}' not found in response")
```

```python
# core/evaluators/json_schema_valid.py
import json
import jsonschema
from core.models import Score


class JsonSchemaEvaluator:
    def __init__(self, schema: dict):
        self.schema = schema

    def _run(self, response: str) -> Score:
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            return Score(value=0.0, reason=f"Invalid JSON: {e}")
        try:
            jsonschema.validate(data, self.schema)
            return Score(value=1.0)
        except jsonschema.ValidationError as e:
            return Score(value=0.0, reason=e.message)
```

```python
# core/evaluators/no_pii.py
import re
from core.models import Score

_PII_PATTERNS = [
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "email address"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "SSN"),
    (re.compile(r"\b\d{16}\b"), "credit card number"),
    (re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"), "phone number"),
]


class NoPiiEvaluator:
    def _run(self, response: str) -> Score:
        for pattern, label in _PII_PATTERNS:
            if pattern.search(response):
                return Score(value=0.0, reason=f"Response contains {label}")
        return Score(value=1.0)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_evaluators.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add core/evaluators/ tests/unit/test_evaluators.py
git commit -m "feat(core): deterministic evaluators — contains, regex, json_schema, no_pii"
```

---

## Task 6: Plugin loader (file-based + entry_points)

**Files:**
- Create: `core/loader.py`
- Create: `tests/unit/test_loader.py`
- Create: `tests/fixtures/plugins/sample_plugin.py`

**Step 1: Create sample plugin fixture**

```python
# tests/fixtures/plugins/sample_plugin.py
from core.plugins import EvaPlugin, EvaSpec
from core.models import Score


class SamplePlugin(EvaPlugin):
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(value=1.0, reason="sample plugin")
```

**Step 2: Write failing tests**

```python
# tests/unit/test_loader.py
from pathlib import Path
import pluggy
from core.loader import load_file_plugin, load_entry_point_plugins, build_manager
from core.models import Score

FIXTURES = Path("tests/fixtures/plugins")


def test_load_file_plugin():
    pm = pluggy.PluginManager("eva")
    load_file_plugin(pm, FIXTURES / "sample_plugin.py")
    results = pm.hook.run_eval(response="hello", context={})
    assert any(r.reason == "sample plugin" for r in results)


def test_load_missing_file_raises():
    pm = pluggy.PluginManager("eva")
    from core.loader import PluginLoadError
    import pytest
    with pytest.raises(PluginLoadError):
        load_file_plugin(pm, Path("nonexistent.py"))


def test_build_manager_includes_builtins():
    pm = build_manager()
    # manager is created without errors
    assert pm is not None
```

**Step 3: Run tests to verify they fail**

```bash
pytest tests/unit/test_loader.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.loader'`

**Step 4: Implement loader**

```python
# core/loader.py
import importlib
import importlib.metadata
import importlib.util
from pathlib import Path

import pluggy

from core.plugins import EvaSpec, make_manager


class PluginLoadError(Exception):
    pass


def load_file_plugin(pm: pluggy.PluginManager, path: Path) -> None:
    if not path.exists():
        raise PluginLoadError(f"Plugin file not found: {path}")
    spec = importlib.util.spec_from_file_location("_eva_user_plugin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Register any EvaPlugin subclasses found in the module
    from core.plugins import EvaPlugin
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, EvaPlugin) and obj is not EvaPlugin:
            pm.register(obj())


def load_entry_point_plugins(pm: pluggy.PluginManager) -> None:
    try:
        eps = importlib.metadata.entry_points(group="eva.evaluators")
        for ep in eps:
            plugin_class = ep.load()
            pm.register(plugin_class())
    except Exception:
        pass  # no entry points installed — that's fine


def build_manager(plugin_file: Path | None = None) -> pluggy.PluginManager:
    pm = make_manager()
    load_entry_point_plugins(pm)
    if plugin_file and plugin_file.exists():
        load_file_plugin(pm, plugin_file)
    return pm
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_loader.py -v
```

Expected: all PASS.

**Step 6: Commit**

```bash
git add core/loader.py tests/unit/test_loader.py tests/fixtures/plugins/
git commit -m "feat(core): plugin loader — file-based and entry_points"
```

---

## Task 7: Dataset loader (YAML + JSONL)

**Files:**
- Create: `core/dataset.py`
- Create: `tests/unit/test_dataset.py`
- Create: `tests/fixtures/datasets/simple.yaml`
- Create: `tests/fixtures/datasets/simple.jsonl`

**Step 1: Create fixture datasets**

```yaml
# tests/fixtures/datasets/simple.yaml
name: refund_suite
target: http://localhost:8000/chat
evaluators:
  - name: contains
    mode: binary
tests:
  - id: test_01
    input: "Refund order 123"
  - id: test_02
    input: "What is my balance?"
    expected_output: "balance"
```

```jsonl
# tests/fixtures/datasets/simple.jsonl
{"id": "test_01", "input": "Refund order 123"}
{"id": "test_02", "input": "What is my balance?", "expected_output": "balance"}
```

**Step 2: Write failing tests**

```python
# tests/unit/test_dataset.py
from pathlib import Path
from core.dataset import load_dataset, Dataset, TestCase

FIXTURES = Path("tests/fixtures/datasets")


def test_load_yaml_dataset():
    ds = load_dataset(FIXTURES / "simple.yaml")
    assert ds.name == "refund_suite"
    assert ds.target == "http://localhost:8000/chat"
    assert len(ds.tests) == 2


def test_load_yaml_test_cases():
    ds = load_dataset(FIXTURES / "simple.yaml")
    assert ds.tests[0].id == "test_01"
    assert ds.tests[0].input == "Refund order 123"
    assert ds.tests[0].expected_output is None
    assert ds.tests[1].expected_output == "balance"


def test_load_jsonl_dataset():
    ds = load_dataset(FIXTURES / "simple.jsonl", target="http://localhost:9000/chat")
    assert len(ds.tests) == 2
    assert ds.target == "http://localhost:9000/chat"


def test_load_jsonl_test_cases():
    ds = load_dataset(FIXTURES / "simple.jsonl", target="http://localhost:9000/chat")
    assert ds.tests[0].id == "test_01"
    assert ds.tests[1].expected_output == "balance"


def test_load_missing_file_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_dataset(Path("nonexistent.yaml"))
```

**Step 3: Run tests to verify they fail**

```bash
pytest tests/unit/test_dataset.py -v
```

Expected: `ModuleNotFoundError`

**Step 4: Implement dataset loader**

```python
# core/dataset.py
import json
from pathlib import Path
from pydantic import BaseModel
import yaml


class TestCase(BaseModel):
    id: str
    input: str
    expected_output: str | None = None
    metadata: dict = {}


class Dataset(BaseModel):
    name: str
    target: str
    evaluators: list[dict] = []
    tests: list[TestCase] = []


def load_dataset(path: Path, target: str | None = None) -> Dataset:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    if path.suffix == ".jsonl":
        if not target:
            raise ValueError("target URL required when loading JSONL datasets")
        tests = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                tests.append(TestCase.model_validate(json.loads(line)))
        return Dataset(name=path.stem, target=target, tests=tests)

    raw = yaml.safe_load(path.read_text())
    if target:
        raw["target"] = target
    tests = [TestCase.model_validate(t) for t in raw.pop("tests", [])]
    return Dataset(tests=tests, **raw)
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_dataset.py -v
```

Expected: all PASS.

**Step 6: Commit**

```bash
git add core/dataset.py tests/unit/test_dataset.py tests/fixtures/datasets/
git commit -m "feat(core): dataset loader — YAML and JSONL formats"
```

---

## Task 8: SQLite storage adapter

**Files:**
- Create: `core/storage.py`
- Create: `tests/unit/test_storage.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_storage.py
import pytest
from datetime import datetime
from core.storage import SqliteStorage
from core.models import Run, Result, Score


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/test.db")


@pytest.fixture
def sample_run():
    return Run(
        run_id="run_001",
        dataset="refunds",
        target="http://localhost:8000",
        started_at=datetime.utcnow(),
        results=[
            Result(
                test_id="t1",
                evaluator="contains",
                score=Score(value=1.0),
                mode="binary",
                duration_ms=42,
                trace_id=None,
            )
        ],
        passed=True,
    )


def test_save_and_retrieve_run(storage, sample_run):
    storage.save_run(sample_run)
    retrieved = storage.get_run("run_001")
    assert retrieved.run_id == "run_001"
    assert retrieved.passed is True


def test_retrieve_results(storage, sample_run):
    storage.save_run(sample_run)
    retrieved = storage.get_run("run_001")
    assert len(retrieved.results) == 1
    assert retrieved.results[0].evaluator == "contains"


def test_missing_run_returns_none(storage):
    assert storage.get_run("nonexistent") is None


def test_list_runs(storage, sample_run):
    storage.save_run(sample_run)
    runs = storage.list_runs()
    assert len(runs) == 1
    assert runs[0].run_id == "run_001"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_storage.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: Implement SQLite storage**

```python
# core/storage.py
import json
from datetime import datetime
from typing import Optional
from sqlmodel import Field, Session, SQLModel, create_engine, select
from core.models import Run, Result, Score


class RunRecord(SQLModel, table=True):
    run_id: str = Field(primary_key=True)
    dataset: str
    target: str
    started_at: datetime
    duration_ms: int
    passed: bool
    results_json: str  # JSON-serialized list of results


class SqliteStorage:
    def __init__(self, db_url: str = "sqlite:///.eva/state.db"):
        self.engine = create_engine(db_url)
        SQLModel.metadata.create_all(self.engine)

    def save_run(self, run: Run) -> None:
        record = RunRecord(
            run_id=run.run_id,
            dataset=run.dataset,
            target=run.target,
            started_at=run.started_at,
            duration_ms=run.duration_ms,
            passed=run.passed,
            results_json=json.dumps([r.model_dump() for r in run.results]),
        )
        with Session(self.engine) as session:
            session.merge(record)
            session.commit()

    def get_run(self, run_id: str) -> Optional[Run]:
        with Session(self.engine) as session:
            record = session.get(RunRecord, run_id)
            if not record:
                return None
            return self._record_to_run(record)

    def list_runs(self) -> list[Run]:
        with Session(self.engine) as session:
            records = session.exec(select(RunRecord)).all()
            return [self._record_to_run(r) for r in records]

    def _record_to_run(self, record: RunRecord) -> Run:
        results = [Result.model_validate(r) for r in json.loads(record.results_json)]
        return Run(
            run_id=record.run_id,
            dataset=record.dataset,
            target=record.target,
            started_at=record.started_at,
            duration_ms=record.duration_ms,
            passed=record.passed,
            results=results,
        )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_storage.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add core/storage.py tests/unit/test_storage.py
git commit -m "feat(core): SQLite storage adapter via SQLModel"
```

---

## Task 9: Runner — sequential execution

**Files:**
- Create: `core/runner.py`
- Create: `tests/unit/test_runner.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_runner.py
import pytest
from unittest.mock import AsyncMock, patch
from core.runner import Runner
from core.dataset import Dataset, TestCase
from core.models import Score
from core.plugins import EvaPlugin, EvaSpec


class AlwaysPassPlugin(EvaPlugin):
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(value=1.0)


class AlwaysFailPlugin(EvaPlugin):
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(value=0.0, reason="always fails")


DATASET = Dataset(
    name="test_suite",
    target="http://fake-agent/chat",
    evaluators=[{"name": "always_pass", "mode": "binary"}],
    tests=[
        TestCase(id="t1", input="hello"),
        TestCase(id="t2", input="world"),
    ],
)


@pytest.mark.asyncio
async def test_runner_all_pass():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok response"

    runner = Runner(pm=pm, call_agent=fake_call)
    run = await runner.execute(DATASET)
    assert run.passed is True
    assert len(run.results) == 2


@pytest.mark.asyncio
async def test_runner_one_fail():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysFailPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "bad response"

    runner = Runner(pm=pm, call_agent=fake_call)
    run = await runner.execute(DATASET)
    assert run.passed is False


@pytest.mark.asyncio
async def test_runner_records_duration():
    from core.plugins import make_manager
    pm = make_manager()
    pm.register(AlwaysPassPlugin())

    async def fake_call(input: str, target: str) -> str:
        return "ok"

    runner = Runner(pm=pm, call_agent=fake_call)
    run = await runner.execute(DATASET)
    assert run.duration_ms >= 0
    assert all(r.duration_ms >= 0 for r in run.results)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_runner.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: Implement runner**

```python
# core/runner.py
import asyncio
import uuid
from datetime import datetime
from typing import Callable, Awaitable

import pluggy

from core.dataset import Dataset
from core.models import Result, Run, Score


class Runner:
    def __init__(
        self,
        pm: pluggy.PluginManager,
        call_agent: Callable[[str, str], Awaitable[str]],
        concurrency: int = 1,
    ):
        self.pm = pm
        self.call_agent = call_agent
        self.concurrency = concurrency

    async def execute(self, dataset: Dataset) -> Run:
        started_at = datetime.utcnow()
        run_id = str(uuid.uuid4())[:8]
        semaphore = asyncio.Semaphore(self.concurrency)
        results = []

        async def run_one(test) -> list[Result]:
            async with semaphore:
                t0 = datetime.utcnow()
                self.pm.hook.before_eval(test_id=test.id, context={})
                response = await self.call_agent(test.input, dataset.target)
                scores: list[Score] = self.pm.hook.run_eval(
                    response=response, context={"test": test.model_dump()}
                )
                t1 = datetime.utcnow()
                duration_ms = int((t1 - t0).total_seconds() * 1000)

                test_results = []
                for score in scores:
                    # Determine mode from dataset evaluator config
                    mode = "binary"
                    min_score = 1.0
                    r = Result(
                        test_id=test.id,
                        evaluator="unknown",
                        score=score,
                        mode=mode,
                        min_score=min_score,
                        duration_ms=duration_ms,
                    )
                    self.pm.hook.after_eval(
                        test_id=test.id, score=score, context={}
                    )
                    test_results.append(r)
                return test_results

        tasks = [run_one(t) for t in dataset.tests]
        all_results = await asyncio.gather(*tasks)
        for batch in all_results:
            results.extend(batch)

        t_end = datetime.utcnow()
        passed = all(r.passed for r in results)
        return Run(
            run_id=run_id,
            dataset=dataset.name,
            target=dataset.target,
            results=results,
            started_at=started_at,
            duration_ms=int((t_end - started_at).total_seconds() * 1000),
            passed=passed,
        )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_runner.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add core/runner.py tests/unit/test_runner.py
git commit -m "feat(core): async runner with semaphore concurrency"
```

---

## Task 10: `eva init` CLI command

**Files:**
- Modify: `cli/main.py`
- Create: `tests/e2e/test_init.py`

**Step 1: Write failing E2E test**

```python
# tests/e2e/test_init.py
import subprocess
import sys
from pathlib import Path


def test_eva_init_creates_structure(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (tmp_path / "evals").is_dir()
    assert (tmp_path / "eva_plugins.py").exists()
    assert (tmp_path / ".env").exists()


def test_eva_init_output_mentions_created(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert "evals" in result.stdout
    assert "eva_plugins.py" in result.stdout


def test_eva_init_idempotent(tmp_path):
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "init"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/e2e/test_init.py -v
```

Expected: non-zero exit code (no `init` command yet)

**Step 3: Implement `eva init`**

```python
# cli/main.py
from pathlib import Path
import typer
from rich.console import Console

app = typer.Typer()
console = Console()

PLUGIN_TEMPLATE = '''\
from eva.core import evaluator, Score

# Example custom evaluator — delete or modify as needed.
# @evaluator(name="my_check", mode="binary")
# def my_check(response: str, context: dict) -> Score:
#     return Score(value=1.0)
'''

ENV_TEMPLATE = '''\
EVA_STORAGE=sqlite:///.eva/state.db
EVA_JUDGE_MODEL=openai/gpt-4o-mini
# OPENAI_API_KEY=
'''


@app.command()
def init():
    """Scaffold Eva project structure in the current directory."""
    cwd = Path.cwd()

    evals_dir = cwd / "evals"
    evals_dir.mkdir(exist_ok=True)
    console.print(f"Created [green]{evals_dir.relative_to(cwd)}/[/green]")

    plugins_file = cwd / "eva_plugins.py"
    if not plugins_file.exists():
        plugins_file.write_text(PLUGIN_TEMPLATE)
    console.print(f"Created [green]{plugins_file.name}[/green]")

    env_file = cwd / ".env"
    if not env_file.exists():
        env_file.write_text(ENV_TEMPLATE)
    console.print(f"Created [green]{env_file.name}[/green]")


if __name__ == "__main__":
    app()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/e2e/test_init.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add cli/main.py tests/e2e/test_init.py
git commit -m "feat(cli): eva init — scaffold project structure"
```

---

## Task 11: `eva contract validate` CLI command

**Files:**
- Modify: `cli/main.py`
- Create: `tests/e2e/test_contract_validate.py`

**Step 1: Write failing E2E tests**

```python
# tests/e2e/test_contract_validate.py
import subprocess
import sys
from pathlib import Path

FIXTURES = Path("tests/fixtures/contracts")


def run_eva(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_validate_valid_contract():
    result = run_eva("contract", "validate", str(FIXTURES / "valid.yaml"))
    assert result.returncode == 0
    assert "valid" in result.stdout.lower()


def test_validate_invalid_contract():
    result = run_eva("contract", "validate", str(FIXTURES / "invalid_missing_name.yaml"))
    assert result.returncode == 1
    assert "error" in result.stdout.lower() or "error" in result.stderr.lower()


def test_validate_missing_file():
    result = run_eva("contract", "validate", "nonexistent.yaml")
    assert result.returncode == 1
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/e2e/test_contract_validate.py -v
```

Expected: non-zero exit code (no `contract` command yet)

**Step 3: Implement `eva contract validate`**

```python
# Add to cli/main.py

contract_app = typer.Typer()
app.add_typer(contract_app, name="contract")


@contract_app.command("validate")
def contract_validate(path: Path = typer.Argument(..., help="Path to contract YAML file")):
    """Validate a contract YAML file."""
    from core.contract import load_contract, ContractValidationError
    try:
        contract = load_contract(path)
        console.print(f"[green]Valid[/green] contract: [bold]{contract.name}[/bold]")
        console.print(f"  Provider: {contract.provider}")
        console.print(f"  Evaluators: {len(contract.evaluators)}")
        raise typer.Exit(0)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ContractValidationError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/e2e/test_contract_validate.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add cli/main.py tests/e2e/test_contract_validate.py
git commit -m "feat(cli): eva contract validate"
```

---

## Task 12: `eva run` CLI command (E2E)

**Files:**
- Modify: `cli/main.py`
- Create: `tests/e2e/test_run.py`
- Create: `tests/fixtures/datasets/e2e_suite.yaml`

**Step 1: Create E2E dataset fixture**

```yaml
# tests/fixtures/datasets/e2e_suite.yaml
name: e2e_suite
target: http://localhost:18999/chat
evaluators:
  - name: contains
    mode: binary
tests:
  - id: t1
    input: "say hello"
    expected_output: "hello"
```

**Step 2: Write failing E2E tests**

Note: these tests spin up a tiny HTTP server to act as the fake agent.

```python
# tests/e2e/test_run.py
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FIXTURES = Path("tests/fixtures/datasets")


class AlwaysHelloHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"hello world")

    def log_message(self, *args):
        pass  # suppress server logs in test output


def start_fake_agent(port: int):
    server = HTTPServer(("localhost", port), AlwaysHelloHandler)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    return server


def run_eva(*args):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
    )


def test_eva_run_all_pass(tmp_path):
    server = start_fake_agent(18999)
    try:
        result = run_eva(
            "run",
            "--dataset", str(FIXTURES / "e2e_suite.yaml"),
            "--target", "http://localhost:18999/chat",
        )
        assert result.returncode == 0
        assert "passed" in result.stdout.lower() or "pass" in result.stdout.lower()
    finally:
        server.shutdown()


def test_eva_run_exit_code_zero_on_pass(tmp_path):
    server = start_fake_agent(18998)
    try:
        result = run_eva(
            "run",
            "--dataset", str(FIXTURES / "e2e_suite.yaml"),
            "--target", "http://localhost:18998/chat",
        )
        assert result.returncode == 0
    finally:
        server.shutdown()
```

**Step 3: Run tests to verify they fail**

```bash
pytest tests/e2e/test_run.py -v
```

Expected: non-zero exit code (no `run` command yet)

**Step 4: Implement `eva run`**

```python
# Add to cli/main.py
import asyncio
import httpx
from core.dataset import load_dataset
from core.loader import build_manager
from core.runner import Runner
from core.storage import SqliteStorage


@app.command()
def run(
    dataset: Path = typer.Option(..., "--dataset", help="Path to eval dataset (YAML or JSONL)"),
    target: str = typer.Option(None, "--target", help="Override target agent URL"),
    concurrency: int = typer.Option(1, "--concurrency", help="Number of concurrent tests"),
):
    """Run evaluations against a target agent."""
    ds = load_dataset(dataset, target=target)
    pm = build_manager(plugin_file=Path("eva_plugins.py"))

    async def call_agent(input: str, target_url: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(target_url, json={"input": input})
            return resp.text

    runner = Runner(pm=pm, call_agent=call_agent, concurrency=concurrency)
    eva_run = asyncio.run(runner.execute(ds))

    # Basic output
    total = len(eva_run.results)
    passed = sum(1 for r in eva_run.results if r.passed)
    for r in eva_run.results:
        icon = "[green]✓[/green]" if r.passed else "[red]✗[/red]"
        console.print(f"  {icon} {r.test_id} ({r.duration_ms}ms)")

    console.print(f"\nResults: {passed}/{total} Passed.")

    storage = SqliteStorage()
    storage.save_run(eva_run)

    raise typer.Exit(0 if eva_run.passed else 1)
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/e2e/test_run.py -v
```

Expected: all PASS.

**Step 6: Run full test suite — everything should be green**

```bash
pytest -v
```

Expected: all PASS.

**Step 7: Commit**

```bash
git add cli/main.py tests/e2e/test_run.py tests/fixtures/datasets/e2e_suite.yaml
git commit -m "feat(cli): eva run — async eval runner with exit codes"
```

---

## Task 13: Final integration smoke test + Phase 1 gate

**Step 1: Run full test suite**

```bash
pytest -v --tb=short
```

Expected: all tests PASS. Note any failures and fix before proceeding.

**Step 2: Manual smoke test**

```bash
# In a fresh temp directory:
mkdir /tmp/eva-smoke && cd /tmp/eva-smoke
eva init
# Should create evals/, eva_plugins.py, .env

eva contract validate /path/to/tests/fixtures/contracts/valid.yaml
# Should print: Valid contract: refund_policy

# Start a fake agent in another terminal:
# python -c "from http.server import HTTPServer, BaseHTTPRequestHandler; ..."

eva run --dataset ./evals/... --target http://localhost:8000/chat
# Should print results table and exit 0
```

**Step 3: Tag Phase 1 complete**

```bash
git tag v0.1.0-phase1
git commit --allow-empty -m "chore: Phase 1 complete — Core Foundation"
```

**Step 4: Lock the interfaces**

The following are now stable and must not change without a migration path:

- `core/models.py` — `Score`, `Result`, `Contract`, `Run`, `RetryPolicy`
- `core/plugins.py` — `EvaSpec` hook signatures (`before_eval`, `run_eval`, `after_eval`)
- `core/contract.py` — `load_contract` signature
- `core/dataset.py` — `Dataset`, `TestCase`
- `core/storage.py` — `SqliteStorage` interface

Team Server may now start on Phase 3 foundations (contract model is stable).

---

## Running All Tests

```bash
# Unit tests only
pytest tests/unit/ -v

# E2E tests only
pytest tests/e2e/ -v

# Full suite
pytest -v
```

## Directory Structure After Phase 1

```
eva/
├── cli/
│   ├── __init__.py
│   └── main.py              # Typer app: init, run, contract validate
├── core/
│   ├── __init__.py
│   ├── py.typed
│   ├── models.py            # Score, Result, Contract, Run, RetryPolicy
│   ├── contract.py          # YAML loader + validation
│   ├── dataset.py           # YAML + JSONL loader
│   ├── plugins.py           # pluggy hook specs + EvaPlugin base
│   ├── loader.py            # file-based + entry_points plugin loader
│   ├── runner.py            # async runner with semaphore
│   ├── storage.py           # SQLite via SQLModel
│   └── evaluators/
│       ├── __init__.py
│       ├── contains.py
│       ├── regex_match.py
│       ├── json_schema_valid.py
│       └── no_pii.py
├── tests/
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_contract.py
│   │   ├── test_dataset.py
│   │   ├── test_plugins.py
│   │   ├── test_loader.py
│   │   ├── test_runner.py
│   │   ├── test_storage.py
│   │   └── test_evaluators.py
│   ├── e2e/
│   │   ├── test_init.py
│   │   ├── test_contract_validate.py
│   │   └── test_run.py
│   └── fixtures/
│       ├── contracts/
│       │   ├── valid.yaml
│       │   └── invalid_missing_name.yaml
│       ├── datasets/
│       │   ├── simple.yaml
│       │   ├── simple.jsonl
│       │   └── e2e_suite.yaml
│       └── plugins/
│           └── sample_plugin.py
└── pyproject.toml
```
