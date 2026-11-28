# core/evaluators/ifeval_check.py
"""``ifeval_check``: IFEval / IFBench instruction verifiers on a reply.

Reads ``instruction_id_list`` and ``kwargs`` from the case ``metadata`` (the
field names of google/IFEval and allenai/IFBench_test) and runs the published
verifiers (vendored in ``core/third_party/ifbench``) against the reply, strict and
loose. The case passes when every listed instruction passes (prompt-level) at
the configured ``pass_on`` level. Deterministic and offline once the ``ifeval``
extra and the nltk data (``eva data fetch``) are installed.
"""
from __future__ import annotations

from typing import Any

from core import nltk_data
from core.chat_targets import split_reasoning
from core.models import Score

EXTRA_HINT = 'pip install "hop-top-eva[ifeval]"'
_registry: dict | None = None


class _SetupError(Exception):
    """Optional dependency or nltk data missing."""


def _load_registry() -> dict:
    global _registry
    if _registry is not None:
        return _registry
    try:
        import nltk  # noqa: F401
        import langdetect  # noqa: F401
        import emoji  # noqa: F401
        import syllapy  # noqa: F401
        import immutabledict  # noqa: F401
    except ImportError as e:
        raise _SetupError(
            f"ifeval_check needs the 'ifeval' extra ({e.name} not installed): "
            f"{EXTRA_HINT}"
        ) from e
    import langdetect
    import nltk

    # langdetect is randomised per call by default; pin it for stable grading.
    langdetect.DetectorFactory.seed = 0
    default = nltk_data.default_dir()
    if str(default) not in nltk.data.path:
        nltk.data.path.append(str(default))
    absent = nltk_data.missing(
        nltk_data.search_dirs(extra=[p for p in nltk.data.path])
    )
    if absent:
        raise _SetupError(
            f"ifeval_check: nltk data missing ({', '.join(absent)}); "
            f"run: {nltk_data.FETCH_COMMAND}"
        )
    from core.third_party.ifbench import instructions_registry

    _registry = instructions_registry.INSTRUCTION_DICT
    return _registry


def _error(msg: str) -> Score:
    return Score(value=0.0, reason=f"error: {msg}", metadata={"error": msg})


def _loose_variants(response: str) -> list[str]:
    """The eight response variants IFEval's loose mode tries."""
    lines = response.split("\n")
    no_first = "\n".join(lines[1:]).strip()
    no_last = "\n".join(lines[:-1]).strip()
    no_both = "\n".join(lines[1:-1]).strip()
    base = [response, no_first, no_last, no_both]
    return base + [v.replace("*", "") for v in base]


class IfevalCheckEvaluator:
    def __init__(
        self,
        pass_on: str = "strict",
        instruction_id_list: list[str] | None = None,
        kwargs: list[dict | None] | None = None,
    ):
        if pass_on not in ("strict", "loose"):
            raise ValueError(f"pass_on must be 'strict' or 'loose'; got {pass_on!r}")
        self.pass_on = pass_on
        self.instruction_id_list = instruction_id_list
        self.kwargs = kwargs

    def run(self, response: str) -> Score:
        return self.run_case(response, {}) or Score(
            value=0.0,
            reason="no instructions: set instruction_id_list or score via a "
            "dataset case with metadata.instruction_id_list",
        )

    def run_case(self, response: str, case: dict) -> Score | None:
        """Score one case; ``None`` = not applicable (no instruction ids)."""
        meta = case.get("metadata") or {}
        ids = meta.get("instruction_id_list", self.instruction_id_list)
        if ids is None:
            return None
        kwargs = meta.get("kwargs", self.kwargs)
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            return _error("instruction_id_list must be a list of strings")
        if not ids:
            return _error("instruction_id_list is empty")
        if kwargs is None:
            kwargs = [{} for _ in ids]
        if not isinstance(kwargs, list) or len(kwargs) != len(ids):
            return _error(
                f"kwargs must be a list with one entry per instruction id "
                f"({len(ids)})"
            )
        if not all(k is None or isinstance(k, dict) for k in kwargs):
            return _error("each kwargs entry must be an object or null")
        try:
            registry = _load_registry()
        except _SetupError as e:
            return _error(str(e))
        unknown = [i for i in ids if i not in registry]
        if unknown:
            return _error(f"unknown instruction id(s): {', '.join(unknown)}")

        answer, _ = split_reasoning(response)
        prompt = case.get("input", "")
        variants = _loose_variants(answer)
        details: list[dict[str, Any]] = []
        for iid, kw in zip(ids, kwargs):
            try:
                inst = registry[iid](iid)
                clean = {k: v for k, v in (kw or {}).items() if v is not None}
                inst.build_description(**clean)
                args = inst.get_instruction_args()
                if args and "prompt" in args:
                    inst.build_description(prompt=prompt)
                strict = bool(
                    answer and answer.strip() and inst.check_following(answer)
                )
                loose = strict or any(
                    v.strip() and inst.check_following(v) for v in variants
                )
            except Exception as e:  # bad kwargs or verifier failure
                return _error(f"{iid}: {type(e).__name__}: {e}")
            details.append({"id": iid, "strict": strict, "loose": loose})

        strict_all = all(d["strict"] for d in details)
        loose_all = all(d["loose"] for d in details)
        passed = strict_all if self.pass_on == "strict" else loose_all
        n = len(details)
        s_n = sum(d["strict"] for d in details)
        l_n = sum(d["loose"] for d in details)
        per = "; ".join(
            f"{d['id']} strict={'pass' if d['strict'] else 'fail'} "
            f"loose={'pass' if d['loose'] else 'fail'}"
            for d in details
        )
        reason = (
            f"strict {'pass' if strict_all else 'fail'} ({s_n}/{n}), "
            f"loose {'pass' if loose_all else 'fail'} ({l_n}/{n}); "
            f"scored on {self.pass_on}: {per}"
        )
        return Score(
            value=1.0 if passed else 0.0,
            reason=reason,
            metadata={
                "strict": strict_all,
                "loose": loose_all,
                "instructions": details,
            },
        )
