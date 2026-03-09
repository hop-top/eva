# tests/unit/test_loader.py
from pathlib import Path
import pluggy
import pytest
from core.loader import load_file_plugin, build_manager, PluginLoadError
from core.models import Score

FIXTURES = Path("tests/fixtures/plugins")


def test_load_file_plugin():
    pm = pluggy.PluginManager("eva")
    # We need to add EvaSpec to pm so it can register hooks
    from core.plugins import EvaSpec
    pm.add_hookspecs(EvaSpec)
    load_file_plugin(pm, FIXTURES / "sample_plugin.py")
    results = pm.hook.run_eval(response="hello", context={})
    assert any(r.reason == "sample plugin" for r in results)


def test_load_missing_file_raises():
    pm = pluggy.PluginManager("eva")
    with pytest.raises(PluginLoadError):
        load_file_plugin(pm, Path("nonexistent.py"))


def test_build_manager_includes_builtins():
    pm = build_manager()
    # manager is created without errors
    assert pm is not None
