# tests/e2e/test_plugin_e2e.py
"""
E2E tests for Taylor's plugin authoring workflow (US-016 to US-020).

Verifies the plugin hook machinery in-process: no subprocess needed.
Covers custom evaluator registration, context propagation, and error isolation.
"""
import importlib
import sys
from pathlib import Path

import pytest

from core.models import Score
from core.plugins import EvaPlugin, EvaSpec, make_manager
from core.dataset import Dataset
from core.runner import Runner


# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------

async def _echo_agent(prompt: str, target: str) -> str:
    """Fake agent: echoes the prompt unchanged."""
    return prompt


def _make_dataset(name: str = "plugin_test", target: str = "http://fake") -> Dataset:
    return Dataset.model_validate(
        {
            "name": name,
            "target": target,
            "evaluators": [{"name": "custom", "mode": "binary"}],
            "tests": [{"id": "p1", "input": "hello", "expected_output": "hello"}],
        }
    )


# ---------------------------------------------------------------------------
# US-016 + US-018: custom EvaPlugin subclass registers and fires run_eval
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_custom_plugin_run_hook_called():
    # US-016: As Taylor, I want to implement a custom evaluator by subclassing `EvaPlugin`
    # so that I can encode domain-specific quality rules without forking Eva.
    # US-018: As Taylor, I want to drop an eva_plugins.py file in the project root so that
    # local one-off evaluators are loaded without packaging overhead.
    """Custom EvaPlugin.run_eval hook is invoked by the Runner."""

    fired = []

    class AlwaysPassPlugin(EvaPlugin):
        @EvaSpec.hook_impl
        def run_eval(self, response: str, context: dict) -> Score:
            fired.append(response)
            return Score(value=1.0, reason="always pass")

    pm = make_manager()
    pm.register(AlwaysPassPlugin())
    runner = Runner(pm=pm, call_agent=_echo_agent, concurrency="sequential")
    run = await runner.execute(_make_dataset())

    assert len(fired) == 1
    assert fired[0] == "hello"
    assert run.passed


# ---------------------------------------------------------------------------
# US-019: context dict contains the full test case
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plugin_receives_full_context():
    # US-019: As Taylor, I want the run_eval hook to receive the full response and context
    # dict so that my evaluator can make fine-grained decisions based on test metadata.
    """run_eval context contains test.id and test.input."""

    captured_contexts = []

    class ContextCapture(EvaPlugin):
        @EvaSpec.hook_impl
        def run_eval(self, response: str, context: dict) -> Score:
            captured_contexts.append(context)
            return Score(value=1.0)

    pm = make_manager()
    pm.register(ContextCapture())
    runner = Runner(pm=pm, call_agent=_echo_agent, concurrency="sequential")
    await runner.execute(_make_dataset())

    assert len(captured_contexts) == 1
    ctx = captured_contexts[0]
    assert "test" in ctx
    assert ctx["test"]["id"] == "p1"
    assert ctx["test"]["input"] == "hello"


# ---------------------------------------------------------------------------
# US-020: plugin error is isolated — run still completes
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "US-020 gap: runner does not yet isolate plugin hook exceptions. "
        "pluggy propagates RuntimeError from run_eval back to the caller. "
        "Fix: wrap pm.hook.run_eval() in try/except in core/runner.py."
    ),
    strict=True,
)
@pytest.mark.asyncio
async def test_plugin_error_does_not_abort_run():
    # US-020: As Taylor, I want plugin errors to be isolated and reported as a failed score
    # rather than crashing the runner so that one bad plugin doesn't abort the whole suite.
    # CURRENT STATE: xfail — runner propagates plugin exceptions (gap documented above).
    """
    A plugin that raises must not propagate out of runner.execute.

    pluggy propagates hook-impl errors by default; the runner should catch and
    convert them to Score(value=0.0) rather than re-raising to the caller.
    This test is marked xfail to track the gap without blocking CI.
    """

    class BrokenPlugin(EvaPlugin):
        @EvaSpec.hook_impl
        def run_eval(self, response: str, context: dict) -> Score:
            raise RuntimeError("plugin internal failure")

    pm = make_manager()
    pm.register(BrokenPlugin())
    runner = Runner(pm=pm, call_agent=_echo_agent, concurrency="sequential")
    run = await runner.execute(_make_dataset())
    assert run is not None


# ---------------------------------------------------------------------------
# US-016: sample_plugin.py fixture loads correctly (local plugin file pattern)
# ---------------------------------------------------------------------------

def test_sample_plugin_fixture_loads():
    # US-016: As Taylor, I want to implement a custom evaluator by subclassing `EvaPlugin`
    # so that I can encode domain-specific quality rules without forking Eva.
    """Fixture sample_plugin.py is importable and registers correctly."""
    fixture_dir = str(Path("tests/fixtures/plugins"))
    sys.path.insert(0, fixture_dir)
    try:
        mod = importlib.import_module("sample_plugin")
        plugin_cls = mod.SamplePlugin
        pm = make_manager()
        pm.register(plugin_cls())
        hooks = pm.get_plugins()
        assert any(isinstance(p, plugin_cls) for p in hooks)
    finally:
        sys.path.pop(0)
        sys.modules.pop("sample_plugin", None)
