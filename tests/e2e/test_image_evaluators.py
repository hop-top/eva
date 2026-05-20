# tests/e2e/test_image_evaluators.py
"""E2E tests: image evaluators wired with mocked LLM."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.dataset import EvaTestCase
from core.evaluators.llm_judge import (
    ImageCoherenceEvaluator,
    ImageEditingEvaluator,
    ImageHelpfulnessEvaluator,
    ImageReferenceEvaluator,
    TextToImageEvaluator,
)
from core.llm import build_vision_message
from core.models import Score


def make_mock_llm(reply: str) -> AsyncMock:
    mock = AsyncMock()
    completion = MagicMock()
    completion.content = reply
    mock.complete = AsyncMock(return_value=completion)
    return mock


TEST_IMAGE_URL = "https://example.com/img.png"


# ---------------------------------------------------------------------------
# TextToImageEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_text_to_image_with_url():
    tc = EvaTestCase(id="tc-i01", input="A sunset over the mountains")
    llm = make_mock_llm("0.9\nImage closely matches the prompt.")
    ev = TextToImageEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="",
        image_url=TEST_IMAGE_URL,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_text_to_image_no_url():
    tc = EvaTestCase(id="tc-i02", input="A sunset over the mountains")
    llm = make_mock_llm("0.9\nWould match.")
    ev = TextToImageEvaluator(llm_adapter=llm)
    score = await ev.evaluate(prompt=tc.input, response="")
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.5)
    assert score.reason == "No image provided"


# ---------------------------------------------------------------------------
# ImageEditingEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_editing():
    tc = EvaTestCase(id="tc-i03", input="Remove the background from the photo")
    llm = make_mock_llm("0.85\nBackground removed successfully.")
    ev = ImageEditingEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="",
        image_url=TEST_IMAGE_URL,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# ImageCoherenceEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_coherence():
    tc = EvaTestCase(id="tc-i04", input="Image of a red car")
    llm = make_mock_llm("0.8\nImage and text are coherent.")
    ev = ImageCoherenceEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="A red sports car parked on the street.",
        image_url=TEST_IMAGE_URL,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# ImageHelpfulnessEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_helpfulness():
    tc = EvaTestCase(id="tc-i05", input="Show me how to tie a knot")
    llm = make_mock_llm("0.75\nImage is helpful for understanding the knot.")
    ev = ImageHelpfulnessEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="",
        image_url=TEST_IMAGE_URL,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# ImageReferenceEvaluator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_reference():
    tc = EvaTestCase(id="tc-i06", input="Describe the image")
    llm = make_mock_llm("0.92\nDescription accurately reflects the image.")
    ev = ImageReferenceEvaluator(llm_adapter=llm)
    score = await ev.evaluate(
        prompt=tc.input,
        response="A golden retriever playing in a park.",
        image_url=TEST_IMAGE_URL,
    )
    assert isinstance(score, Score)
    assert score.value == pytest.approx(0.92)


# ---------------------------------------------------------------------------
# build_vision_message structure
# ---------------------------------------------------------------------------

def test_vision_message_structure():
    msg = build_vision_message("Describe this image.", TEST_IMAGE_URL)

    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)

    content = msg["content"]
    assert any(part.get("type") == "text" for part in content)

    image_parts = [p for p in content if p.get("type") == "image_url"]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"] == TEST_IMAGE_URL
