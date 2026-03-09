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
