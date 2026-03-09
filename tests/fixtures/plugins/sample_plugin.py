# tests/fixtures/plugins/sample_plugin.py
from core.plugins import EvaPlugin, EvaSpec
from core.models import Score


class SamplePlugin(EvaPlugin):
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(value=1.0, reason="sample plugin")
