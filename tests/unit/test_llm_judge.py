# tests/unit/test_llm_judge.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.evaluators.llm_judge import (
    parse_score,
    RelevanceEvaluator,
    HallucinationEvaluator,
    ToneEvaluator,
    TaskCompletionEvaluator,
    SafetyEvaluator,
    BiasEvaluator,
    ToxicityEvaluator,
    SummarizationEvaluator,
    PromptAlignmentEvaluator,
    GoalAccuracyEvaluator,
    ToolCorrectnessEvaluator,
    ArgumentCorrectnessEvaluator,
    ToolUseEvaluator,
    StepEfficiencyEvaluator,
    PlanAdherenceEvaluator,
    PlanQualityEvaluator,
    GEvalEvaluator,
    FaithfulnessEvaluator,
    ContextualRecallEvaluator,
    ContextualPrecisionEvaluator,
    ContextualRelevancyEvaluator,
    AnswerRelevancyEvaluator,
    RAGASEvaluator,
    TextToImageEvaluator,
    ImageEditingEvaluator,
    ImageCoherenceEvaluator,
    ImageHelpfulnessEvaluator,
    ImageReferenceEvaluator,
)
from core.models import Score


# ---------------------------------------------------------------------------
# parse_score helper
# ---------------------------------------------------------------------------

def test_parse_score_basic():
    value, reason = parse_score("0.8\nLooks good")
    assert value == pytest.approx(0.8)
    assert reason == "Looks good"


def test_parse_score_no_reason():
    value, reason = parse_score("1.0")
    assert value == pytest.approx(1.0)
    assert reason == ""


def test_parse_score_clamps_above_one():
    value, _ = parse_score("1.5")
    assert value == pytest.approx(1.0)


def test_parse_score_clamps_below_zero():
    value, _ = parse_score("-0.3")
    assert value == pytest.approx(0.0)


def test_parse_score_fallback_on_garbage():
    value, reason = parse_score("not a number\nexplanation")
    assert value == pytest.approx(0.5)
    assert "not a number" in reason


def test_parse_score_fallback_on_empty():
    value, _ = parse_score("")
    assert value == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Shared mock factory
# ---------------------------------------------------------------------------

def make_mock_llm(reply: str) -> AsyncMock:
    mock = AsyncMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


# ---------------------------------------------------------------------------
# RelevanceEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_relevance_evaluator_passes_score():
    llm = make_mock_llm("0.9\nHighly relevant response.")
    ev = RelevanceEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="What is Python?", response="Python is a language.")
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)
    assert "Highly relevant" in score.reason


@pytest.mark.asyncio
async def test_relevance_evaluator_fallback():
    llm = make_mock_llm("oops")
    ev = RelevanceEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# HallucinationEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hallucination_evaluator():
    llm = make_mock_llm("0.2\nContains several false facts.")
    ev = HallucinationEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.2)
    assert score.metadata["evaluator_id"] == "hallucination"


# ---------------------------------------------------------------------------
# ToneEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tone_evaluator_default_professional():
    llm = make_mock_llm("0.7\nMostly professional tone.")
    ev = ToneEvaluator(llm_adapter=llm)
    assert ev.expected_tone == "professional"
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_tone_evaluator_custom_tone():
    llm = make_mock_llm("0.5\nPartially casual.")
    ev = ToneEvaluator(llm_adapter=llm, expected_tone="casual")
    assert ev.expected_tone == "casual"
    # Judge prompt should mention expected tone
    await ev.evaluate(prompt="q", response="r")
    call_args = llm.complete.call_args
    assert "casual" in call_args[0][0][0]["content"]


# ---------------------------------------------------------------------------
# TaskCompletionEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_completion_evaluator():
    llm = make_mock_llm("1.0\nFully addressed.")
    ev = TaskCompletionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(1.0)
    assert score.metadata["evaluator_id"] == "task_completion"


# ---------------------------------------------------------------------------
# SafetyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safety_evaluator_safe():
    llm = make_mock_llm("1.0\nNo harmful content.")
    ev = SafetyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_safety_evaluator_unsafe():
    llm = make_mock_llm("0.0\nHarmful content detected.")
    ev = SafetyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.0)
    assert score.metadata["evaluator_id"] == "safety"


# ---------------------------------------------------------------------------
# BiasEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bias_evaluator_biased():
    llm = make_mock_llm("0.1\nStrongly biased language detected.")
    ev = BiasEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.1)
    assert score.metadata["evaluator_id"] == "bias"


@pytest.mark.asyncio
async def test_bias_evaluator_unbiased():
    llm = make_mock_llm("0.9\nNo bias detected.")
    ev = BiasEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# ToxicityEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toxicity_evaluator_toxic():
    llm = make_mock_llm("0.1\nExtremely toxic language.")
    ev = ToxicityEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.1)
    assert score.metadata["evaluator_id"] == "toxicity"


@pytest.mark.asyncio
async def test_toxicity_evaluator_non_toxic():
    llm = make_mock_llm("0.95\nCompletely non-toxic response.")
    ev = ToxicityEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="q", response="r")
    assert score.value == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# SummarizationEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarization_evaluator_with_source():
    llm = make_mock_llm("0.85\nFaithfully captures key facts.")
    ev = SummarizationEvaluator(llm_adapter=llm, source_text="The sky is blue and the sun is hot.")
    score = await ev.evaluate(prompt="Summarize this.", response="The sky is blue.")
    assert score.value == pytest.approx(0.85)
    assert score.metadata["evaluator_id"] == "summarization"
    call_args = llm.complete.call_args
    assert "source text" in call_args[0][0][0]["content"].lower()


@pytest.mark.asyncio
async def test_summarization_evaluator_without_source():
    llm = make_mock_llm("0.7\nDecent quality summary.")
    ev = SummarizationEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="Summarize this.", response="A short summary.")
    assert score.value == pytest.approx(0.7)
    call_args = llm.complete.call_args
    assert "quality" in call_args[0][0][0]["content"].lower()


# ---------------------------------------------------------------------------
# PromptAlignmentEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_alignment_evaluator_aligned():
    llm = make_mock_llm("0.95\nAll instructions followed perfectly.")
    ev = PromptAlignmentEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="Write in bullet points.", response="- Item one\n- Item two")
    assert score.value == pytest.approx(0.95)
    assert score.metadata["evaluator_id"] == "prompt_alignment"


@pytest.mark.asyncio
async def test_prompt_alignment_evaluator_misaligned():
    llm = make_mock_llm("0.2\nResponse ignored most instructions.")
    ev = PromptAlignmentEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt="Write in bullet points.", response="Here is some prose.")
    assert score.value == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# GoalAccuracyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_goal_accuracy_evaluator_accurate():
    llm = make_mock_llm("0.9\nMatches expected output closely.")
    ev = GoalAccuracyEvaluator(llm_adapter=llm, expected_output="Paris")
    score = await ev.evaluate(prompt="What is the capital of France?", response="Paris")
    assert score.value == pytest.approx(0.9)
    assert score.metadata["evaluator_id"] == "goal_accuracy"
    call_args = llm.complete.call_args
    assert "Paris" in call_args[0][0][0]["content"]


@pytest.mark.asyncio
async def test_goal_accuracy_evaluator_inaccurate():
    llm = make_mock_llm("0.1\nDoes not match expected output.")
    ev = GoalAccuracyEvaluator(llm_adapter=llm, expected_output="Paris")
    score = await ev.evaluate(prompt="What is the capital of France?", response="London")
    assert score.value == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# T-0174: EvaTestCase planned_steps parsing
# ---------------------------------------------------------------------------

def test_eva_test_case_planned_steps_parses():
    import yaml
    from core.dataset import EvaTestCase

    raw = yaml.safe_load("""
id: test-1
input: do the thing
planned_steps:
  - step1
  - step2
""")
    tc = EvaTestCase.model_validate(raw)
    assert tc.planned_steps == ["step1", "step2"]


def test_eva_test_case_planned_steps_optional():
    from core.dataset import EvaTestCase

    tc = EvaTestCase.model_validate({"id": "t1", "input": "hello"})
    assert tc.planned_steps is None


# ---------------------------------------------------------------------------
# T-0165: ToolCorrectnessEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_correctness_matching_tools():
    llm = make_mock_llm("0.9\nCorrect tools used.")
    ev = ToolCorrectnessEvaluator(llm_adapter=llm)
    tool_events = [{"tool_name": "search", "args": {"q": "foo"}, "result": "bar"}]
    score = await ev.evaluate(
        prompt="Find foo",
        response="Found foo",
        tool_events=tool_events,
        expected_tools=["search"],
    )
    assert score.value == pytest.approx(0.9)
    assert score.metadata["evaluator_id"] == "tool_correctness"


@pytest.mark.asyncio
async def test_tool_correctness_wrong_tools():
    llm = make_mock_llm("0.1\nWrong tools used.")
    ev = ToolCorrectnessEvaluator(llm_adapter=llm)
    tool_events = [{"tool_name": "delete", "args": {}, "result": None}]
    score = await ev.evaluate(
        prompt="Find foo",
        response="Deleted something",
        tool_events=tool_events,
        expected_tools=["search"],
    )
    assert score.value == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# T-0166: ArgumentCorrectnessEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_argument_correctness_correct_args():
    llm = make_mock_llm("0.95\nArguments match expected.")
    ev = ArgumentCorrectnessEvaluator(llm_adapter=llm)
    tool_events = [{"tool_name": "search", "args": {"q": "python"}}]
    score = await ev.evaluate(
        prompt="Search python",
        response="Results",
        tool_events=tool_events,
        expected_args={"search": {"q": "python"}},
    )
    assert score.value == pytest.approx(0.95)
    assert score.metadata["evaluator_id"] == "argument_correctness"


@pytest.mark.asyncio
async def test_argument_correctness_wrong_args():
    llm = make_mock_llm("0.2\nArguments differ significantly.")
    ev = ArgumentCorrectnessEvaluator(llm_adapter=llm)
    tool_events = [{"tool_name": "search", "args": {"q": "java"}}]
    score = await ev.evaluate(
        prompt="Search python",
        response="Java results",
        tool_events=tool_events,
        expected_args={"search": {"q": "python"}},
    )
    assert score.value == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# T-0167: ToolUseEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_use_efficient():
    llm = make_mock_llm("0.9\nTools used efficiently.")
    ev = ToolUseEvaluator(llm_adapter=llm)
    tool_events = [{"tool_name": "search", "args": {"q": "weather"}}]
    score = await ev.evaluate(
        prompt="What is the weather?",
        response="It is sunny.",
        tool_events=tool_events,
    )
    assert score.value == pytest.approx(0.9)
    assert score.metadata["evaluator_id"] == "tool_use"


@pytest.mark.asyncio
async def test_tool_use_misused():
    llm = make_mock_llm("0.1\nTools not used when needed.")
    ev = ToolUseEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is the weather?",
        response="I don't know.",
        tool_events=[],
    )
    assert score.value == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# T-0175: StepEfficiencyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_step_efficiency_optimal():
    llm = make_mock_llm("1.0\nOptimal number of steps.")
    ev = StepEfficiencyEvaluator(llm_adapter=llm)
    tool_events = [{"tool_name": "search", "args": {}}]
    score = await ev.evaluate(
        prompt="Find info",
        response="Here it is.",
        planned_steps=["search for info"],
        tool_events=tool_events,
    )
    assert score.value == pytest.approx(1.0)
    assert score.metadata["evaluator_id"] == "step_efficiency"


@pytest.mark.asyncio
async def test_step_efficiency_inefficient():
    llm = make_mock_llm("0.2\nFar too many steps.")
    ev = StepEfficiencyEvaluator(llm_adapter=llm)
    tool_events = [{"tool_name": f"t{i}", "args": {}} for i in range(10)]
    score = await ev.evaluate(
        prompt="Find info",
        response="Eventually found it.",
        planned_steps=["search for info"],
        tool_events=tool_events,
    )
    assert score.value == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# T-0176: PlanAdherenceEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_adherence_followed():
    llm = make_mock_llm("0.95\nAll planned steps followed.")
    ev = PlanAdherenceEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="Do the task",
        response="Step 1 done. Step 2 done.",
        planned_steps=["step 1", "step 2"],
    )
    assert score.value == pytest.approx(0.95)
    assert score.metadata["evaluator_id"] == "plan_adherence"


@pytest.mark.asyncio
async def test_plan_adherence_deviated():
    llm = make_mock_llm("0.3\nSignificant deviation from plan.")
    ev = PlanAdherenceEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="Do the task",
        response="Did something entirely different.",
        planned_steps=["step 1", "step 2"],
    )
    assert score.value == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# T-0177: PlanQualityEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_quality_good():
    llm = make_mock_llm("0.9\nWell-structured and feasible plan.")
    ev = PlanQualityEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="Build a web scraper",
        response="1. Identify target URLs. 2. Fetch HTML. 3. Parse. 4. Store.",
    )
    assert score.value == pytest.approx(0.9)
    assert score.metadata["evaluator_id"] == "plan_quality"


@pytest.mark.asyncio
async def test_plan_quality_poor():
    llm = make_mock_llm("0.2\nVague and incomplete plan.")
    ev = PlanQualityEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="Build a web scraper",
        response="Just do it somehow.",
    )
    assert score.value == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# T-0178: GEvalEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_geval_conciseness_meets_criteria():
    llm = make_mock_llm("0.85\nResponse is concise.")
    ev = GEvalEvaluator(llm_adapter=llm, criteria="Response must be under 20 words", name="conciseness")
    score = await ev.evaluate(prompt="Explain gravity", response="Gravity pulls objects together.")
    assert score.value == pytest.approx(0.85)
    assert score.metadata["evaluator_id"] == "conciseness"
    call_args = llm.complete.call_args
    assert "under 20 words" in call_args[0][0][0]["content"]


@pytest.mark.asyncio
async def test_geval_custom_criteria_fails():
    llm = make_mock_llm("0.1\nDoes not meet criteria.")
    ev = GEvalEvaluator(llm_adapter=llm, criteria="Must include a code example", name="has_code")
    score = await ev.evaluate(prompt="Show me Python", response="Python is a language.")
    assert score.value == pytest.approx(0.1)
    assert score.metadata["evaluator_id"] == "has_code"


# ---------------------------------------------------------------------------
# T-0169: EvaTestCase retrieval_context parsing
# ---------------------------------------------------------------------------

def test_eva_test_case_retrieval_context_parses():
    import yaml
    from core.dataset import EvaTestCase

    raw = yaml.safe_load("""
id: rag-test-1
input: what is the capital of France?
retrieval_context: "France is a country in Western Europe. Its capital city is Paris."
expected_output: Paris
""")
    tc = EvaTestCase.model_validate(raw)
    assert tc.retrieval_context == "France is a country in Western Europe. Its capital city is Paris."
    assert tc.expected_output == "Paris"


# ---------------------------------------------------------------------------
# T-0170: FaithfulnessEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_faithfulness_with_retrieval_context():
    llm = make_mock_llm("0.95\nAll claims grounded in context.")
    ev = FaithfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is Paris?",
        response="Paris is the capital of France.",
        retrieval_context="France is a country. Its capital is Paris.",
    )
    assert score.value == pytest.approx(0.95)
    assert score.metadata["evaluator_id"] == "faithfulness"
    call_args = llm.complete.call_args
    assert "retrieval context" in call_args[0][0][0]["content"].lower()


@pytest.mark.asyncio
async def test_faithfulness_without_retrieval_context():
    llm = make_mock_llm("0.6\nPartially grounded.")
    ev = FaithfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is Paris?",
        response="Paris is in France.",
    )
    assert score.value == pytest.approx(0.6)
    assert score.metadata["evaluator_id"] == "faithfulness"


# ---------------------------------------------------------------------------
# T-0171: ContextualRecallEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contextual_recall_with_context_kwarg():
    llm = make_mock_llm("0.9\nContext fully covers expected output.")
    ev = ContextualRecallEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is the capital of France?",
        response="Paris",
        retrieval_context="Paris is the capital of France.",
        expected_output="Paris",
    )
    assert score.value == pytest.approx(0.9)
    assert score.metadata["evaluator_id"] == "contextual_recall"


@pytest.mark.asyncio
async def test_contextual_recall_with_constructor_expected():
    llm = make_mock_llm("0.4\nContext only partially covers needed info.")
    ev = ContextualRecallEvaluator(llm_adapter=llm, expected_output="Paris is beautiful")
    score = await ev.evaluate(
        prompt="Describe Paris",
        response="Paris is a city.",
        retrieval_context="Paris is in France.",
    )
    assert score.value == pytest.approx(0.4)
    call_args = llm.complete.call_args
    assert "Paris is beautiful" in call_args[0][0][0]["content"]


# ---------------------------------------------------------------------------
# T-0172: ContextualPrecisionEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contextual_precision_high():
    llm = make_mock_llm("0.95\nAll retrieved chunks highly relevant.")
    ev = ContextualPrecisionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is the capital of France?",
        response="Paris",
        retrieval_context="Paris is the capital of France.",
    )
    assert score.value == pytest.approx(0.95)
    assert score.metadata["evaluator_id"] == "contextual_precision"


@pytest.mark.asyncio
async def test_contextual_precision_low():
    llm = make_mock_llm("0.2\nMost retrieved content is off-topic.")
    ev = ContextualPrecisionEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is the capital of France?",
        response="Unknown",
        retrieval_context="Germany won the World Cup. Italy has great food.",
    )
    assert score.value == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# T-0163: ContextualRelevancyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_contextual_relevancy_high():
    llm = make_mock_llm("0.9\nContext highly relevant to query.")
    ev = ContextualRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is Python?",
        response="Python is a programming language.",
        retrieval_context="Python is a high-level programming language known for readability.",
    )
    assert score.value == pytest.approx(0.9)
    assert score.metadata["evaluator_id"] == "contextual_relevancy"


@pytest.mark.asyncio
async def test_contextual_relevancy_low():
    llm = make_mock_llm("0.1\nContext unrelated to query.")
    ev = ContextualRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is Python?",
        response="Irrelevant answer.",
        retrieval_context="The history of ancient Rome.",
    )
    assert score.value == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# T-0164: AnswerRelevancyEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_relevancy_direct():
    llm = make_mock_llm("0.95\nDirectly and completely answers the query.")
    ev = AnswerRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is 2 + 2?",
        response="2 + 2 equals 4.",
    )
    assert score.value == pytest.approx(0.95)
    assert score.metadata["evaluator_id"] == "answer_relevancy"


@pytest.mark.asyncio
async def test_answer_relevancy_off_topic():
    llm = make_mock_llm("0.05\nResponse does not answer the question.")
    ev = AnswerRelevancyEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt="What is 2 + 2?",
        response="I like pizza.",
    )
    assert score.value == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# T-0173: RAGASEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ragas_evaluator_averages_component_scores():
    from unittest.mock import AsyncMock as _AM

    async def make_mock_ev(ev_id, val):
        class _Ev:
            evaluator_id = ev_id

            async def evaluate(self, prompt, response, **ctx):
                return Score(
                    value=val,
                    reason=f"reason-{ev_id}",
                    metadata={"evaluator_id": ev_id},
                )
        return _Ev()

    ev1 = await make_mock_ev("faithfulness", 0.8)
    ev2 = await make_mock_ev("contextual_relevancy", 0.6)
    ev3 = await make_mock_ev("answer_relevancy", 1.0)

    ragas = RAGASEvaluator(evaluators=[ev1, ev2, ev3])
    score = await ragas.evaluate(prompt="q", response="r")

    assert score.value == pytest.approx((0.8 + 0.6 + 1.0) / 3)
    assert score.metadata["evaluator_id"] == "ragas"
    assert score.metadata["component_scores"]["faithfulness"] == pytest.approx(0.8)
    assert score.metadata["component_scores"]["contextual_relevancy"] == pytest.approx(0.6)
    assert score.metadata["component_scores"]["answer_relevancy"] == pytest.approx(1.0)
