"""Judge provider settings: eva.yaml `judge:` keys, env overrides, adapter args.

`litellm.acompletion` is always mocked; no request leaves the process.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.config import EvaConfig, JudgeConfig, find_and_load_config
from core.llm import JudgeConfigError, build_llm_adapter


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("EVA_JUDGE_MODEL", "EVA_JUDGE_BASE_URL", "MY_JUDGE_KEY"):
        monkeypatch.delenv(k, raising=False)


def _fake_response():
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="0.9\nok"))],
        usage=None,
        model="m",
    )


def test_config_parses_judge_keys(tmp_path):
    (tmp_path / "eva.yaml").write_text(
        "judge:\n"
        "  model: openai/my-model\n"
        "  base_url: http://localhost:11434/v1\n"
        "  api_key_env: MY_JUDGE_KEY\n"
        "  timeout_s: 45\n"
    )
    j = find_and_load_config(tmp_path).judge
    assert j.model == "openai/my-model"
    assert j.base_url == "http://localhost:11434/v1"
    assert j.api_key_env == "MY_JUDGE_KEY"
    assert j.timeout_s == 45


def test_config_defaults_unset():
    j = EvaConfig().judge
    assert (j.base_url, j.api_key_env, j.timeout_s) == (None, None, None)


def test_adapter_none_without_model_even_with_base_url(monkeypatch):
    monkeypatch.setenv("EVA_JUDGE_BASE_URL", "http://x/v1")
    assert build_llm_adapter(EvaConfig()) is None


def test_adapter_kwargs_from_config(monkeypatch):
    monkeypatch.setenv("MY_JUDGE_KEY", "secret-from-env")
    cfg = EvaConfig(
        judge=JudgeConfig(
            model="openai/m",
            base_url="http://localhost:11434/v1",
            api_key_env="MY_JUDGE_KEY",
            timeout_s=45,
            params={"temperature": 0},
        )
    )
    a = build_llm_adapter(cfg)
    assert a.model == "openai/m"
    assert a.kwargs == {
        "temperature": 0,
        "api_base": "http://localhost:11434/v1",
        "api_key": "secret-from-env",
        "timeout": 45,
    }


def test_env_base_url_overrides_config(monkeypatch):
    monkeypatch.setenv("EVA_JUDGE_BASE_URL", "http://env-host/v1")
    cfg = EvaConfig(judge=JudgeConfig(model="openai/m", base_url="http://cfg-host/v1"))
    assert build_llm_adapter(cfg).kwargs["api_base"] == "http://env-host/v1"


def test_model_only_adds_no_extra_kwargs():
    a = build_llm_adapter(EvaConfig(judge=JudgeConfig(model="gpt-4o-mini")))
    assert a.kwargs == {}


def test_params_api_key_not_clobbered_by_placeholder():
    cfg = EvaConfig(
        judge=JudgeConfig(model="openai/m", base_url="http://h/v1", params={"api_key": "p"})
    )
    assert build_llm_adapter(cfg).kwargs["api_key"] == "p"


def test_custom_endpoint_without_key_env_ignores_ambient_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient")
    cfg = EvaConfig(judge=JudgeConfig(model="openai/m", base_url="http://h/v1"))
    assert build_llm_adapter(cfg).kwargs["api_key"] == "none"


def test_named_key_env_unset_raises(monkeypatch):
    cfg = EvaConfig(judge=JudgeConfig(model="openai/m", api_key_env="MY_JUDGE_KEY"))
    with pytest.raises(JudgeConfigError, match="MY_JUDGE_KEY"):
        build_llm_adapter(cfg)


@pytest.mark.asyncio
async def test_complete_passes_endpoint_args_to_litellm(monkeypatch):
    monkeypatch.setenv("MY_JUDGE_KEY", "k-123")
    cfg = EvaConfig(
        judge=JudgeConfig(
            model="openai/m",
            base_url="http://localhost:11434/v1",
            api_key_env="MY_JUDGE_KEY",
            timeout_s=12.5,
        )
    )
    adapter = build_llm_adapter(cfg)
    with patch("litellm.acompletion", new_callable=AsyncMock) as m:
        m.return_value = _fake_response()
        out = await adapter.complete([{"role": "user", "content": "hi"}])
    assert out.content == "0.9\nok"
    kw = m.call_args.kwargs
    assert kw["model"] == "openai/m"
    assert kw["api_base"] == "http://localhost:11434/v1"
    assert kw["api_key"] == "k-123"
    assert kw["timeout"] == 12.5
    assert kw["messages"] == [{"role": "user", "content": "hi"}]
