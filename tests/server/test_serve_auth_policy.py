# tests/server/test_serve_auth_policy.py
"""`eva serve` auth policy: key store required unless --no-auth.

`serve_auth_mode` decides; `EVA_NO_AUTH` (set by `eva serve --no-auth`, not a
user-facing switch) carries the choice to the process that builds the app.
"""
import pytest

from server.app import create_app
from server.auth import (
    ApiKeyMiddleware,
    AuthNotConfiguredError,
    auth_enabled,
    serve_auth_mode,
)

STORE = {"EVA_REDIS_URL": "redis://key-store.invalid:6379/0"}


def test_no_store_no_flag_refuses():
    with pytest.raises(AuthNotConfiguredError) as exc:
        serve_auth_mode(no_auth=False, environ={})
    msg = str(exc.value)
    assert "EVA_REDIS_URL" in msg
    assert "--no-auth" in msg


def test_no_store_flag_serves_unauthenticated():
    assert serve_auth_mode(no_auth=True, environ={}) == "disabled"


def test_store_no_flag_enforces():
    assert serve_auth_mode(no_auth=False, environ=STORE) == "enforced"


def test_flag_wins_over_store():
    assert serve_auth_mode(no_auth=True, environ=STORE) == "disabled"


def test_blank_store_counts_as_unset():
    with pytest.raises(AuthNotConfiguredError):
        serve_auth_mode(no_auth=False, environ={"EVA_REDIS_URL": ""})


def _has_auth(app) -> bool:
    return any(m.cls is ApiKeyMiddleware for m in app.user_middleware)


def test_env_no_auth_wins_over_store_in_create_app(monkeypatch):
    monkeypatch.setenv("EVA_REDIS_URL", STORE["EVA_REDIS_URL"])
    monkeypatch.setenv("EVA_NO_AUTH", "1")
    assert auth_enabled() is False
    assert not _has_auth(create_app())


def test_create_app_default_unchanged(monkeypatch):
    monkeypatch.delenv("EVA_NO_AUTH", raising=False)
    monkeypatch.setenv("EVA_REDIS_URL", STORE["EVA_REDIS_URL"])
    assert _has_auth(create_app())
    monkeypatch.delenv("EVA_REDIS_URL")
    assert not _has_auth(create_app())
