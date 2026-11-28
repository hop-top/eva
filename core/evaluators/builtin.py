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
LLM configured) pass ``None``; LLM-judge factories raise
``JudgeAdapterRequired`` rather than silently registering broken instances.
Any other ``ValueError`` / ``KeyError`` / ``TypeError`` from a factory is an
invalid config; build through ``core.evaluators.errors.build_evaluator`` to get
it as ``EvaluatorConfigError``.

Adding a new built-in evaluator: register it here. Both call sites pick it
up automatically.
"""
from __future__ import annotations

import re
from typing import Any, Callable

import jsonschema

from core.evaluators import config_values as cv

from core.evaluators.answer_match import ExactMatchEvaluator, FinalAnswerEvaluator
from core.evaluators.citation import CitationEvaluator
from core.evaluators.code_block_runs import CodeBlockRunsEvaluator
from core.evaluators.code_test_passes import CodeTestPassesEvaluator
from core.evaluators.code_tests import CodeTestsEvaluator
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.own_mode import OWN_MODE, check_pass_mode
from core.evaluators.errors import EvaluatorConfigError, JudgeAdapterRequired
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
from core.evaluators.ifeval_check import IfevalCheckEvaluator
from core.evaluators.json_path import JsonPathEvaluator
from core.evaluators.key_facts import make_key_facts
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.language import LanguageEvaluator
from core.evaluators.llm_judge import (
    HallucinationEvaluator,
    RelevanceEvaluator,
    SafetyEvaluator,
    TaskCompletionEvaluator,
    ToneEvaluator,
)
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
from core.evaluators.tool_call_match import MODES as TOOL_CALL_MODES, ToolCallMatchEvaluator
from core.evaluators.tool_correctness import ToolCorrectnessEvaluator
from core.evaluators.tool_use import ToolUseEvaluator
from core.evaluators.word_count import WordCountEvaluator


EvaluatorFactory = Callable[[dict, Any | None], Any]


def _require_llm(llm: Any | None, name: str) -> Any:
    """Raise a clear error if a judge-based factory was called without an adapter."""
    if llm is None:
        raise JudgeAdapterRequired(
            f"evaluator {name!r} requires an llm_adapter; none was provided"
        )
    return llm


def _json_schema(cfg: dict, _llm: Any) -> Any:
    schema = cv.mapping(cfg, "schema")  # {} accepts anything
    try:
        jsonschema.validators.validator_for(schema).check_schema(schema)
    except jsonschema.SchemaError as e:
        raise EvaluatorConfigError(f"schema is not a valid JSON Schema: {e.message}") from e
    return JsonSchemaEvaluator(schema=schema)


def _status_code(cfg: dict, _llm: Any) -> Any:
    return StatusCodeEvaluator(
        step=cv.opt_string(cfg, "step"),
        expected=cv.opt_integer(cfg, "expected"),
        expected_in=cv.opt_integers(cfg, "expected_in"),
    )


def _equals(cfg: dict, _llm: Any) -> Any:
    return EqualsEvaluator(
        field=cv.opt_string(cfg, "field"),
        # Preserve the _MISSING sentinel so the evaluator can distinguish
        # "expected absent from YAML" (raise) from "expected: null" (valid).
        expected=cfg["expected"] if "expected" in cfg else _EQUALS_MISSING,
        step=cv.opt_string(cfg, "step"),
    )


def _refusal(cfg: dict, _llm: Any) -> Any:
    # ``mode`` is only the pass mode; the evaluator's setting is ``refusal_mode``.
    check_pass_mode("refusal", cfg.get("mode"))
    return RefusalEvaluator(
        mode=cv.choice(cfg, "refusal_mode", "forbid", OWN_MODE["refusal"][1]),
    )


def _sentence_paragraph_count(cfg: dict, _llm: Any) -> Any:
    check_pass_mode("sentence_paragraph_count", cfg.get("mode"))
    return SentenceParagraphCountEvaluator(
        mode=cv.choice(
            cfg, "count_mode", "sentence", OWN_MODE["sentence_paragraph_count"][1]
        ),
        min=cv.opt_integer(cfg, "min"),
        max=cv.opt_integer(cfg, "max"),
    )


# Programmatic factories read every key through ``config_values`` so a
# wrong-typed value is an EvaluatorConfigError naming the key. Keep a new
# programmatic evaluator's keys on that path.
BUILTIN_EVALUATOR_FACTORIES: dict[str, EvaluatorFactory] = {
    # Programmatic evaluators — ignore the llm_adapter
    "contains": lambda cfg, _llm: ContainsEvaluator(
        substring=cv.string(cfg, "substring"),
        case_sensitive=cv.boolean(cfg, "case_sensitive", True),
        field=cv.opt_string(cfg, "field"),
    ),
    "regex": lambda cfg, _llm: RegexEvaluator(
        pattern=cv.pattern(cfg, "pattern"),
        field=cv.opt_string(cfg, "field"),
    ),
    "json_schema_valid": _json_schema,
    "last_paragraph_regex": lambda cfg, _llm: LastParagraphRegexEvaluator(
        pattern=cv.pattern(
            cfg, "pattern",
            flags=0 if cv.boolean(cfg, "case_sensitive", True) else re.IGNORECASE,
        ),
        case_sensitive=cv.boolean(cfg, "case_sensitive", True),
    ),
    "no_pii": lambda cfg, _llm: NoPiiEvaluator(),
    "word_count": lambda cfg, _llm: WordCountEvaluator(
        max=cv.opt_integer(cfg, "max"),
        min=cv.opt_integer(cfg, "min"),
    ),

    # Flow exec / step assertion (pre-expansion backlog) — programmatic.
    # ``status_code`` and ``exit_code`` are aliases pointing at the same
    # class (status_code.py exports ExitCodeEvaluator = StatusCodeEvaluator);
    # both names register so contracts using either keyword resolve to a
    # factory and don't silent-skip in the gateway / CLI.
    "status_code": _status_code,
    "exit_code": _status_code,
    "equals": _equals,

    # P1 Tier-1 new (agent A) — programmatic
    "mood": lambda cfg, _llm: MoodEvaluator(
        expected=cv.string(cfg, "expected", "imperative"),
    ),
    "language": lambda cfg, _llm: LanguageEvaluator(
        expected=cv.string(cfg, "expected", "en"),
    ),
    "forbidden_phrases": lambda cfg, _llm: ForbiddenPhrasesEvaluator(
        banlist=cv.strings(cfg, "banlist"),
        whole_word=cv.boolean(cfg, "whole_word", True),
        case_sensitive=cv.boolean(cfg, "case_sensitive", False),
    ),
    "refusal": _refusal,

    # P2 Tier-2 structure (agent D) — programmatic
    "citation": lambda cfg, _llm: CitationEvaluator(
        allowed_sources=cv.strings(cfg, "allowed_sources"),
        require_citation=cv.boolean(cfg, "require_citation", False),
    ),
    "code_block_runs": lambda cfg, _llm: CodeBlockRunsEvaluator(
        unsupported_action=cv.choice(cfg, "unsupported_action", "skip", ("skip", "fail")),
        require_code_block=cv.boolean(cfg, "require_code_block", False),
    ),
    "code_test_passes": lambda cfg, _llm: CodeTestPassesEvaluator(
        test_code=cv.string(cfg, "test_code"),
        timeout=cv.seconds(cfg, "timeout", 10),
    ),
    # Dataset-mode scoring against per-case fields (``run_case``): see
    # docs/evaluators-reference.md. ``code_tests`` EXECUTES model output.
    "code_tests": lambda cfg, _llm: CodeTestsEvaluator(
        language=cv.string(cfg, "language", "python"),
        timeout=cv.seconds(cfg, "timeout", 10),
        test_code=cv.string(cfg, "test_code"),
        memory_mb=cv.integer(cfg, "memory_mb", 512),
        max_file_mb=cv.integer(cfg, "max_file_mb", 16),
        partial=cv.boolean(cfg, "partial", False),
        require_isolation=cv.boolean(cfg, "require_isolation", False),
    ),
    # Tool-call log vs the case's metadata.expected_calls; deterministic.
    "tool_call_match": lambda cfg, _llm: ToolCallMatchEvaluator(
        match=cv.choice(cfg, "match", "single", TOOL_CALL_MODES),
        case_sensitive=cv.boolean(cfg, "case_sensitive", True),
        normalize_whitespace=cv.boolean(cfg, "normalize_whitespace", False),
    ),
    "exact_match": lambda cfg, _llm: ExactMatchEvaluator(
        expected=cfg.get("expected"),
    ),
    "final_answer": lambda cfg, _llm: FinalAnswerEvaluator(
        expected=cfg.get("expected"),
    ),
    "ifeval_check": lambda cfg, _llm: IfevalCheckEvaluator(
        pass_on=cv.string(cfg, "pass_on", "strict"),
        instruction_id_list=cv.opt_strings(cfg, "instruction_id_list"),
        kwargs=cv.opt_mappings(cfg, "kwargs"),
    ),
    "key_facts": make_key_facts,
    "json_path": lambda cfg, _llm: JsonPathEvaluator(
        path=cv.string(cfg, "path"),
        comparator=cv.string(cfg, "comparator", "eq"),
        expected=cfg.get("expected"),
    ),
    "markdown_structure": lambda cfg, _llm: MarkdownStructureEvaluator(
        required_h2=cv.strings(cfg, "required_h2"),
        required_code_langs=cv.strings(cfg, "required_code_langs"),
        disallow_broken_local_links=cv.boolean(cfg, "disallow_broken_local_links", False),
    ),
    "sentence_paragraph_count": _sentence_paragraph_count,

    # Generic LLM-judge (legacy, llm_judge.py) — registered so dataset mode
    # and contracts can reference them; previously only in EVALUATOR_REGISTRY.
    "relevance": lambda cfg, llm: RelevanceEvaluator(
        llm_adapter=_require_llm(llm, "relevance"),
    ),
    "hallucination": lambda cfg, llm: HallucinationEvaluator(
        llm_adapter=_require_llm(llm, "hallucination"),
    ),
    "tone": lambda cfg, llm: ToneEvaluator(
        llm_adapter=_require_llm(llm, "tone"),
        expected_tone=cfg.get("expected_tone", "professional"),
    ),
    "task_completion": lambda cfg, llm: TaskCompletionEvaluator(
        llm_adapter=_require_llm(llm, "task_completion"),
    ),
    "safety": lambda cfg, llm: SafetyEvaluator(
        llm_adapter=_require_llm(llm, "safety"),
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
        assertion=cv.string(cfg, "assertion"),
        llm_adapter=llm if llm is not None else cfg.get("llm_adapter"),
        mode=cv.string(cfg, "assertion_mode", "auto"),
    ),
}
