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

## Best Practices for Plugin Authors

1.  **Inherit from `EvaPlugin`**: This ensures your class is correctly identified by the loader.
2.  **Stateless Implementations**: Avoid storing state within your evaluator instance unless absolutely necessary, as instances may be reused across multiple runs.
3.  **Graceful Error Handling**: Catch exceptions within your `run_eval` implementation and return a `Score` with `value=0.0` and a clear `reason`.
4.  **Leverage Metadata**: Use the `Score.metadata` dictionary to return detailed diagnostics that can be used for debugging or displayed in your monitoring dashboard.
5.  **Use Context**: The `context` dictionary contains the full `test` case details, allowing your evaluator to be dynamic based on specific test requirements.
