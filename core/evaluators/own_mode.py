# core/evaluators/own_mode.py
"""``mode`` is only the pass mode (binary|threshold|warn).

``refusal`` and ``sentence_paragraph_count`` have a setting of their own; it
lives under ``refusal_mode`` / ``count_mode``. A ``mode`` that is one of their
own values is rejected naming the key to use. Consulted wherever ``mode`` is
read from user config: the factories (dataset entry, gateway ``config``),
``EvaluatorRef`` (contract) and the gateway ``EvaluatorSpec``.
"""
from __future__ import annotations

from typing import Any

from core.evaluators.errors import EvaluatorConfigError

PASS_MODES = ("binary", "threshold", "warn")

# evaluator -> (key for its own setting, its values)
OWN_MODE: dict[str, tuple[str, tuple[str, ...]]] = {
    "refusal": ("refusal_mode", ("forbid", "require")),
    "sentence_paragraph_count": ("count_mode", ("sentence", "paragraph")),
}


def check_pass_mode(name: str, mode: Any) -> None:
    """Raise unless ``mode`` is unset or a pass mode (only for evaluators in ``OWN_MODE``)."""
    own = OWN_MODE.get(name)
    if own is None or mode is None or (isinstance(mode, str) and mode in PASS_MODES):
        return
    key, values = own
    if isinstance(mode, str) and mode in values:
        msg = f"evaluator {name!r}: mode {mode!r} is not a pass mode; set {key}: {mode}"
    else:
        msg = (
            f"evaluator {name!r}: mode {mode!r} is not a pass mode "
            f"({', '.join(PASS_MODES)}); the evaluator's own setting is {key}"
        )
    raise EvaluatorConfigError(msg, evaluator=name)
