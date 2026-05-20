# core/evaluators/__init__.py
from core.evaluators.argument_correctness import ArgumentCorrectnessEvaluator
from core.evaluators.citation import CitationEvaluator
from core.evaluators.code_block_runs import CodeBlockRunsEvaluator
from core.evaluators.code_test_passes import CodeTestPassesEvaluator
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.content_quality import (
    ContentBiasEvaluator,
    ContentGoalAccuracyEvaluator,
    ContentPromptAlignmentEvaluator,
    ContentSummarizationEvaluator,
    ContentToxicityEvaluator,
)
from core.evaluators.equals import EqualsEvaluator
from core.evaluators.forbidden_phrases import ForbiddenPhrasesEvaluator
from core.evaluators.geval import GEvalEvaluator
from core.evaluators.json_path import JsonPathEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.language import LanguageEvaluator
from core.evaluators.last_paragraph_regex import LastParagraphRegexEvaluator
from core.evaluators.llm_judge import (
    HallucinationEvaluator,
    RelevanceEvaluator,
    SafetyEvaluator,
    TaskCompletionEvaluator,
    ToneEvaluator,
    parse_score,
)
from core.evaluators.markdown_structure import MarkdownStructureEvaluator
from core.evaluators.mood import MoodEvaluator
from core.evaluators.no_pii import NoPiiEvaluator
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
from core.evaluators.status_code import ExitCodeEvaluator, StatusCodeEvaluator
from core.evaluators.step_efficiency import StepEfficiencyEvaluator
from core.evaluators.tool_correctness import ToolCorrectnessEvaluator
from core.evaluators.tool_use import ToolUseEvaluator
from core.evaluators.word_count import WordCountEvaluator

# Name -> class registry. Used by contract loader to resolve `name:`
# references in YAML. exit_code is an alias for status_code —
# both names resolve to the same class. RAG and content-quality evaluators
# use domain-prefixed keys (rag:*, content:*) to avoid name collisions with
# legacy same-named classes in llm_judge.py.
EVALUATOR_REGISTRY = {
    # Programmatic
    "contains": ContainsEvaluator,
    "regex": RegexEvaluator,
    "json_schema_valid": JsonSchemaEvaluator,
    "last_paragraph_regex": LastParagraphRegexEvaluator,
    "no_pii": NoPiiEvaluator,
    "status_code": StatusCodeEvaluator,
    "exit_code": ExitCodeEvaluator,  # alias for status_code
    "equals": EqualsEvaluator,
    "word_count": WordCountEvaluator,

    # Generic LLM-judge (legacy, llm_judge.py)
    "relevance": RelevanceEvaluator,
    "hallucination": HallucinationEvaluator,
    "tone": ToneEvaluator,
    "task_completion": TaskCompletionEvaluator,
    "safety": SafetyEvaluator,

    # P1 Tier-1 new (agent A) — programmatic
    "mood": MoodEvaluator,
    "language": LanguageEvaluator,
    "forbidden_phrases": ForbiddenPhrasesEvaluator,
    "refusal": RefusalEvaluator,

    # P1 US-032 tool-use (agent B) — LLM-judge
    "tool_correctness": ToolCorrectnessEvaluator,
    "argument_correctness": ArgumentCorrectnessEvaluator,
    "tool_use": ToolUseEvaluator,
    "step_efficiency": StepEfficiencyEvaluator,
    "plan_adherence": PlanAdherenceEvaluator,
    "plan_quality": PlanQualityEvaluator,
    "geval": GEvalEvaluator,

    # P2 RAG (agent C) — LLM-judge, domain-prefixed
    "rag:faithfulness": RAGFaithfulnessEvaluator,
    "rag:contextual_relevancy": RAGContextualRelevancyEvaluator,
    "rag:contextual_precision": RAGContextualPrecisionEvaluator,
    "rag:contextual_recall": RAGContextualRecallEvaluator,
    "rag:answer_relevancy": RAGAnswerRelevancyEvaluator,
    "ragas": RAGASEvaluator,

    # P2 content quality (agent C) — LLM-judge, domain-prefixed
    "content:bias": ContentBiasEvaluator,
    "content:toxicity": ContentToxicityEvaluator,
    "content:summarization": ContentSummarizationEvaluator,
    "content:prompt_alignment": ContentPromptAlignmentEvaluator,
    "content:goal_accuracy": ContentGoalAccuracyEvaluator,

    # P2 Tier-2 structure (agent D) — programmatic
    "citation": CitationEvaluator,
    "code_block_runs": CodeBlockRunsEvaluator,
    "code_test_passes": CodeTestPassesEvaluator,
    "json_path": JsonPathEvaluator,
    "markdown_structure": MarkdownStructureEvaluator,
    "sentence_paragraph_count": SentenceParagraphCountEvaluator,

    # Prose-assertion dispatcher (agent E)
    "prose_assertion": ProseAssertionEvaluator,
}

__all__ = [
    "ContainsEvaluator",
    "RegexEvaluator",
    "JsonSchemaEvaluator",
    "LastParagraphRegexEvaluator",
    "NoPiiEvaluator",
    "StatusCodeEvaluator",
    "ExitCodeEvaluator",
    "EqualsEvaluator",
    "WordCountEvaluator",
    "RelevanceEvaluator",
    "HallucinationEvaluator",
    "ToneEvaluator",
    "TaskCompletionEvaluator",
    "SafetyEvaluator",
    "MoodEvaluator",
    "LanguageEvaluator",
    "ForbiddenPhrasesEvaluator",
    "RefusalEvaluator",
    "ToolCorrectnessEvaluator",
    "ArgumentCorrectnessEvaluator",
    "ToolUseEvaluator",
    "StepEfficiencyEvaluator",
    "PlanAdherenceEvaluator",
    "PlanQualityEvaluator",
    "GEvalEvaluator",
    "RAGFaithfulnessEvaluator",
    "RAGContextualRelevancyEvaluator",
    "RAGContextualPrecisionEvaluator",
    "RAGContextualRecallEvaluator",
    "RAGAnswerRelevancyEvaluator",
    "RAGASEvaluator",
    "ContentBiasEvaluator",
    "ContentToxicityEvaluator",
    "ContentSummarizationEvaluator",
    "ContentPromptAlignmentEvaluator",
    "ContentGoalAccuracyEvaluator",
    "CitationEvaluator",
    "CodeBlockRunsEvaluator",
    "CodeTestPassesEvaluator",
    "JsonPathEvaluator",
    "MarkdownStructureEvaluator",
    "SentenceParagraphCountEvaluator",
    "ProseAssertionEvaluator",
    "EVALUATOR_REGISTRY",
    "parse_score",
]
