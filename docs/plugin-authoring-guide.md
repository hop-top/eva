# Plugin Authoring Guide — Eva

Eva is built on a modular architecture using the `pluggy` library. This allows you to extend Eva by creating custom plugins for evaluators, storage adapters, or state management.

---

## The Hook System

Eva defines its plugin interface via **Hook Specifications** (hookspecs). To implement a plugin, you write a class with **Hook Implementations** (hook_impls) that match these specs.

### Core Hook Specifications (`EvaSpec`)

| Hook | Arguments | Description |
|---|---|---|
| `before_eval` | `test_id`, `context` | Runs before an evaluator is executed. |
| `run_eval` | `response`, `context` | **Main hook**. Runs the evaluator. Must return a `Score`. |
| `after_eval` | `test_id`, `score`, `context` | Runs after an evaluator completes. |

---

## 1. Local Plugins (`eva_plugins.py`)

The fastest way to add a custom evaluator is to use the `eva_plugins.py` file in your project root. Eva loads this file automatically during its initialization.

### Example: Creating a `LengthEvaluator`

```python
# eva_plugins.py
from core.plugins import EvaPlugin, EvaSpec
from core.models import Score

class LengthEvaluator(EvaPlugin):
    """Ensures the response is not too long."""
    
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        max_length = context.get("test", {}).get("max_length", 200)
        
        if len(response) <= max_length:
            return Score(value=1.0)
        
        return Score(
            value=0.0, 
            reason=f"Response length {len(response)} exceeds max {max_length}"
        )
```

---

## 2. Package-Based Plugins (`entry_points`)

For reusable plugins that you want to distribute, you can create a Python package and register it using `entry_points` in your `pyproject.toml`.

### Step 1: Implement your plugin

```python
# my_plugin/evaluators.py
from core.plugins import EvaPlugin, EvaSpec
from core.models import Score

class MyCustomEvaluator(EvaPlugin):
    @EvaSpec.hook_impl
    def run_eval(self, response: str, context: dict) -> Score:
        return Score(value=1.0, metadata={"source": "my-custom-plugin"})
```

### Step 2: Register in `pyproject.toml`

```toml
[project.entry-points."eva.evaluators"]
my_evaluator = "my_plugin.evaluators:MyCustomEvaluator"
```

Once installed via `pip`, Eva will automatically discover and load this plugin.

---

## Emitting tool events

Every case gets its own `EventSink` in `context["event_sink"]`. A hook
implementation (usually `before_eval`) can record the tool calls an agent
made; Eva has no other way to see calls made inside a remote agent. Chat
targets need no plugin: their tool calls are logged automatically (see
[Tool-call log](evaluators-reference.md#tool-call-log)).

```python
class RecordTools(EvaPlugin):
    @EvaSpec.hook_impl
    def before_eval(self, test_id: str, context: dict) -> None:
        sink = context["event_sink"]
        sink.emit_tool_call("search", {"q": "refund"}, result={"hits": 2}, duration_ms=7)
        sink.emit_tool_call("lookup", {"id": 1}, error="not found")
```

`emit_tool_call(tool_name, args, *, result=None, error=None, duration_ms=None,
trace_id=None, span_id=None, step_index=None, started_at=None, raw_args=None)`
stores and returns a `ToolCallEvent` (`core/events.py`). `step_index`
defaults to the call's position. Evaluators read the events from
`context["tool_events"]`; after the case, Eva stores one tool-call row per
event with the invocation. `NullEventSink` is the no-op sink used when no
per-case sink exists; its `emit_tool_call` discards the call.

---

## Best Practices for Plugin Authors

1.  **Inherit from `EvaPlugin`**: This ensures your class is correctly identified by the loader.
2.  **Stateless Implementations**: Avoid storing state within your evaluator instance unless absolutely necessary, as instances may be reused across multiple runs.
3.  **Graceful Error Handling**: Catch exceptions within your `run_eval` implementation and return a `Score` with `value=0.0` and a clear `reason`.
4.  **Leverage Metadata**: Use the `Score.metadata` dictionary to return detailed diagnostics that can be used for debugging or displayed in your monitoring dashboard.
5.  **Use Context**: The `context` dictionary contains the full `test` case details, allowing your evaluator to be dynamic based on specific test requirements.
