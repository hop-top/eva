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
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"Could not load plugin from {path}")
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
