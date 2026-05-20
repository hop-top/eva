# core/evaluators/builtin.py
"""Built-in evaluator factory registry.

Single source of truth used by both the gateway (server/gateway/routes.py)
and the standalone CLI (cli/run_contract.py). Each factory takes a config
dict and an optional LLM adapter, returning an evaluator instance with a
`run(response: str) -> Score` method (or `evaluate(...)` for async judge-
based evaluators).

The two-argument signature (cfg, llm_adapter) lets LLM-judge evaluators
declare their adapter dependency explicitly while letting programmatic
evaluators ignore it. Callers that have no adapter (e.g. CLI without an
LLM configured) pass ``None``; LLM-judge factories should raise a clear
error rather than silently registering broken instances.

Adding a new built-in evaluator: register it here. Both call sites pick it
up automatically.
"""
from __future__ import annotations

from typing import Any, Callable

from core.evaluators.citation import CitationEvaluator
from core.evaluators.code_block_runs import CodeBlockRunsEvaluator
from core.evaluators.code_test_passes import CodeTestPassesEvaluator
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.equals import EqualsEvaluator, _MISSING as _EQUALS_MISSING
from core.evaluators.content_quality import (
    ContentBiasEvaluator,
    ContentGoalAccuracyEvaluator,
    ContentPromptAlignmentEvaluator,
    ContentSummarizationEvaluator,
    ContentToxicityEvaluator,
)
from core.evaluators.forbidden_phrases import ForbiddenPhrasesEvaluator
from core.evaluators.geval import GEvalEvaluator
from core.evaluators.json_path import JsonPathEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.language import LanguageEvaluator
from core.evaluators.last_paragraph_regex import LastParagraphRegexEvaluator
from core.evaluators.markdown_structure import MarkdownStructureEvaluator
from core.evaluators.mood import MoodEvaluator
from core.evaluators.no_pii import NoPiiEvaluator
from core.evaluators.argument_correctness import ArgumentCorrectnessEvaluator
from core.evaluators.plan_adherence import PlanAdherenceEvaluator
from core.evaluators.plan_quality import PlanQualityEvaluator
from core.evaluators.prose_assertion import ProseAssertionEvaluator
from core.evaluators.rag import (
    RAGAnswerRelevancyEvaluator,
    RAGASEvaluator,
    RAGContextualPrecisionEvaluator,
    RAGContextualRecallEvaluator,
    RAGContextualRelevancyEvaluator,
    RAGFaithfulnessEvaluator,
)
from core.evaluators.refusal import RefusalEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.sentence_paragraph_count import SentenceParagraphCountEvaluator
from core.evaluators.status_code import StatusCodeEvaluator
from core.evaluators.step_efficiency import StepEfficiencyEvaluator
from core.evaluators.tool_correctness import ToolCorrectnessEvaluator
from core.evaluators.tool_use import ToolUseEvaluator
from core.evaluators.word_count import WordCountEvaluator


EvaluatorFactory = Callable[[dict, Any | None], Any]


def _require_llm(llm: Any | None, name: str) -> Any:
    """Raise a clear error if a judge-based factory was called without an adapter."""
    if llm is None:
        raise ValueError(
            f"evaluator {name!r} requires an llm_adapter; none was provided"
        )
    return llm


BUILTIN_EVALUATOR_FACTORIES: dict[str, EvaluatorFactory] = {
    # Programmatic evaluators — ignore the llm_adapter
    "contains": lambda cfg, _llm: ContainsEvaluator(
        substring=cfg.get("substring", ""),
        case_sensitive=cfg.get("case_sensitive", True),
    ),
    "regex": lambda cfg, _llm: RegexEvaluator(pattern=cfg.get("pattern", ".*")),
    "json_schema_valid": lambda cfg, _llm: JsonSchemaEvaluator(schema=cfg.get("schema", {})),
    "last_paragraph_regex": lambda cfg, _llm: LastParagraphRegexEvaluator(
        pattern=cfg.get("pattern", ".*"),
        case_sensitive=cfg.get("case_sensitive", True),
    ),
    "no_pii": lambda cfg, _llm: NoPiiEvaluator(),
    "word_count": lambda cfg, _llm: WordCountEvaluator(
        max=cfg.get("max"),
        min=cfg.get("min"),
    ),

    # Flow exec / step assertion (pre-expansion backlog) — programmatic.
    # ``status_code`` and ``exit_code`` are aliases pointing at the same
    # class (status_code.py exports ExitCodeEvaluator = StatusCodeEvaluator);
    # both names register so contracts using either keyword resolve to a
    # factory and don't silent-skip in the gateway / CLI.
    "status_code": lambda cfg, _llm: StatusCodeEvaluator(
        step=cfg.get("step"),
        expected=cfg.get("expected"),
        expected_in=cfg.get("expected_in"),
    ),
    "exit_code": lambda cfg, _llm: StatusCodeEvaluator(
        step=cfg.get("step"),
        expected=cfg.get("expected"),
        expected_in=cfg.get("expected_in"),
    ),
    "equals": lambda cfg, _llm: EqualsEvaluator(
        field=cfg.get("field"),
        # Preserve the _MISSING sentinel so the evaluator can distinguish
        # "expected absent from YAML" (raise) from "expected: null" (valid).
        expected=cfg["expected"] if "expected" in cfg else _EQUALS_MISSING,
        step=cfg.get("step"),
    ),

    # P1 Tier-1 new (agent A) — programmatic
    "mood": lambda cfg, _llm: MoodEvaluator(
        expected=cfg.get("expected", "imperative"),
    ),
    "language": lambda cfg, _llm: LanguageEvaluator(
        expected=cfg.get("expected", "en"),
    ),
    "forbidden_phrases": lambda cfg, _llm: ForbiddenPhrasesEvaluator(
        banlist=cfg.get("banlist", []),
        whole_word=cfg.get("whole_word", True),
        case_sensitive=cfg.get("case_sensitive", False),
    ),
    "refusal": lambda cfg, _llm: RefusalEvaluator(
        mode=cfg.get("mode", "forbid"),
    ),

    # P2 Tier-2 structure (agent D) — programmatic
    "citation": lambda cfg, _llm: CitationEvaluator(
        allowed_sources=cfg.get("allowed_sources", []),
        require_citation=cfg.get("require_citation", False),
    ),
    "code_block_runs": lambda cfg, _llm: CodeBlockRunsEvaluator(
        unsupported_action=cfg.get("unsupported_action", "skip"),
        require_code_block=cfg.get("require_code_block", False),
    ),
    "code_test_passes": lambda cfg, _llm: CodeTestPassesEvaluator(
        test_code=cfg.get("test_code", ""),
        timeout=cfg.get("timeout", 10),
    ),
    "json_path": lambda cfg, _llm: JsonPathEvaluator(
        path=cfg.get("path", ""),
        comparator=cfg.get("comparator", "eq"),
        expected=cfg.get("expected"),
    ),
    "markdown_structure": lambda cfg, _llm: MarkdownStructureEvaluator(
        required_h2=cfg.get("required_h2", []),
        required_code_langs=cfg.get("required_code_langs", []),
        disallow_broken_local_links=cfg.get("disallow_broken_local_links", False),
    ),
    "sentence_paragraph_count": lambda cfg, _llm: SentenceParagraphCountEvaluator(
        mode=cfg.get("mode", "sentence"),
        min=cfg.get("min"),
        max=cfg.get("max"),
    ),

    # P1 US-032 tool-use (agent B) — LLM-judge
    "tool_correctness": lambda cfg, llm: ToolCorrectnessEvaluator(
        llm_adapter=_require_llm(llm, "tool_correctness"),
    ),
    "argument_correctness": lambda cfg, llm: ArgumentCorrectnessEvaluator(
        llm_adapter=_require_llm(llm, "argument_correctness"),
    ),
    "tool_use": lambda cfg, llm: ToolUseEvaluator(
        llm_adapter=_require_llm(llm, "tool_use"),
    ),
    "step_efficiency": lambda cfg, llm: StepEfficiencyEvaluator(
        llm_adapter=_require_llm(llm, "step_efficiency"),
    ),
    "plan_adherence": lambda cfg, llm: PlanAdherenceEvaluator(
        llm_adapter=_require_llm(llm, "plan_adherence"),
    ),
    "plan_quality": lambda cfg, llm: PlanQualityEvaluator(
        llm_adapter=_require_llm(llm, "plan_quality"),
    ),
    "geval": lambda cfg, llm: GEvalEvaluator(
        llm_adapter=_require_llm(llm, "geval"),
        criteria=cfg["criteria"],
        name=cfg.get("name", "geval"),
    ),

    # P2 RAG (agent C) — LLM-judge, domain-prefixed keys
    "rag:faithfulness": lambda cfg, llm: RAGFaithfulnessEvaluator(
        llm_adapter=_require_llm(llm, "rag:faithfulness"),
    ),
    "rag:contextual_relevancy": lambda cfg, llm: RAGContextualRelevancyEvaluator(
        llm_adapter=_require_llm(llm, "rag:contextual_relevancy"),
    ),
    "rag:contextual_precision": lambda cfg, llm: RAGContextualPrecisionEvaluator(
        llm_adapter=_require_llm(llm, "rag:contextual_precision"),
    ),
    "rag:contextual_recall": lambda cfg, llm: RAGContextualRecallEvaluator(
        llm_adapter=_require_llm(llm, "rag:contextual_recall"),
        expected_output=cfg.get("expected_output"),
    ),
    "rag:answer_relevancy": lambda cfg, llm: RAGAnswerRelevancyEvaluator(
        llm_adapter=_require_llm(llm, "rag:answer_relevancy"),
    ),
    "ragas": lambda cfg, llm: RAGASEvaluator(
        llm_adapter=_require_llm(llm, "ragas"),
    ),

    # P2 content quality (agent C) — LLM-judge, domain-prefixed keys
    "content:bias": lambda cfg, llm: ContentBiasEvaluator(
        llm_adapter=_require_llm(llm, "content:bias"),
    ),
    "content:toxicity": lambda cfg, llm: ContentToxicityEvaluator(
        llm_adapter=_require_llm(llm, "content:toxicity"),
    ),
    "content:summarization": lambda cfg, llm: ContentSummarizationEvaluator(
        llm_adapter=_require_llm(llm, "content:summarization"),
        source_text=cfg.get("source_text"),
    ),
    "content:prompt_alignment": lambda cfg, llm: ContentPromptAlignmentEvaluator(
        llm_adapter=_require_llm(llm, "content:prompt_alignment"),
    ),
    "content:goal_accuracy": lambda cfg, llm: ContentGoalAccuracyEvaluator(
        llm_adapter=_require_llm(llm, "content:goal_accuracy"),
        expected_output=cfg.get("expected_output"),
    ),

    # Prose-assertion (agent E) — adapter from second arg, ``assertion_mode``
    # from cfg (T-0380). ``assertion_mode`` is set by core/contract.py when the
    # YAML uses the dict-shaped assertion form with judge: / programmatic_only:
    # overrides; bare-string assertions omit it and the evaluator defaults to
    # mode='auto'.
    "prose_assertion": lambda cfg, llm: ProseAssertionEvaluator(
        assertion=cfg.get("assertion", ""),
        llm_adapter=llm if llm is not None else cfg.get("llm_adapter"),
        mode=cfg.get("assertion_mode", "auto"),
    ),
}
