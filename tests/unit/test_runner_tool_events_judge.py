"""Runner path: judge tool evaluators receive ToolCallEvent objects."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.dataset import Dataset, EvaTestCase
from core.plugins import EvaPlugin, EvaSpec, make_manager
from core.runner import Runner


class _Emit(EvaPlugin):
    @EvaSpec.hook_impl
    def before_eval(self, test_id: str, context: dict) -> None:
        sink = context["event_sink"]
        sink.emit_tool_call("search", {"q": "foo"}, step_index=0)
        sink.emit_tool_call("fetch", {"url": "u"}, step_index=1)


def _llm():
    llm = AsyncMock()
    completion = MagicMock()
    completion.content = "0.8\nfine"
    llm.complete = AsyncMock(return_value=completion)
    return llm


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["tool_correctness", "argument_correctness", "tool_use"])
async def test_judge_tool_evaluators_score_runner_events(name):
    pm = make_manager()
    pm.register(_Emit())

    async def agent(prompt, target):
        return "done"

    llm = _llm()
    ds = Dataset(
        name="d", target="http://fake",
        evaluators=[{"name": name, "mode": "binary", "min_score": 0.5}],
        tests=[EvaTestCase(id="t1", input="go")],
    )
    run = await Runner(pm=pm, call_agent=agent, llm_adapter=llm).execute(ds)

    assert [r.score.value for r in run.results] == [0.8]
    sent = llm.complete.call_args.args[0][0]["content"]
    assert '"tool": "search"' in sent and '"tool": "fetch"' in sent
    assert '"q": "foo"' in sent
