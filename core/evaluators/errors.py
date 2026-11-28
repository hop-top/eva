# core/evaluators/errors.py
"""Evaluator build errors: bad config vs a judge that has no adapter.

A factory can fail for two different reasons, and callers must not mix them:

* ``JudgeAdapterRequired``: a judge-based evaluator was built without an LLM
  adapter. The evaluator is unavailable here; callers skip it with a reason.
* ``EvaluatorConfigError``: the evaluator's configuration is invalid. Callers
  fail (dataset run: before any target call; contract mode: exit 2).

Both are ``ValueError`` subclasses so pydantic validators and the contract and
gateway paths, which key off ``ValueError``, keep working.
"""
from __future__ import annotations

import re
from typing import Any, Callable


class EvaluatorConfigError(ValueError):
    """An evaluator's configuration is invalid; ``evaluator`` names it."""

    def __init__(self, message: str, evaluator: str | None = None):
        super().__init__(message)
        self.evaluator = evaluator


class JudgeAdapterRequired(ValueError):
    """A judge-based evaluator was built without an LLM adapter (not a config error)."""


def build_evaluator(
    name: str, factory: Callable[[dict, Any], Any], cfg: dict, llm: Any | None
) -> Any:
    """Build one evaluator; any failure is ``JudgeAdapterRequired`` or ``EvaluatorConfigError``.

    A factory's ``ValueError`` (bad value), ``KeyError`` (missing key),
    ``TypeError`` (wrong type) or ``re.error`` (bad pattern) is invalid config: nothing else a factory
    raises means "skip me".
    """
    try:
        return factory(cfg, llm)
    except JudgeAdapterRequired:
        raise
    except EvaluatorConfigError as e:
        if e.evaluator is not None:  # already names its evaluator
            raise
        detail = str(e)
    except KeyError as e:
        detail = f"missing required key {e.args[0]!r}" if e.args else "missing required key"
    except re.error as e:
        detail = f"invalid regular expression {e.pattern!r}: {e.msg}"
    except (ValueError, TypeError) as e:
        detail = str(e)
        prefix = f"{name}: "
        if detail.startswith(prefix):
            detail = detail[len(prefix):]
    else:  # pragma: no cover - unreachable
        raise AssertionError
    raise EvaluatorConfigError(f"evaluator {name!r}: {detail}", evaluator=name)
