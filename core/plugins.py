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
