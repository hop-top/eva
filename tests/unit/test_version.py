"""Version is read from the real distribution name (hop-top-eva)."""
import importlib
import importlib.metadata as md

import pytest

DIST = "hop-top-eva"
FAKE = "9.8.7"


@pytest.fixture
def only_real_dist(monkeypatch):
    """Only the real distribution name resolves; anything else is not found."""

    def fake_version(name):
        if name == DIST:
            return FAKE
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", fake_version)
    yield
    monkeypatch.undo()
    import cli.main
    import server.app

    importlib.reload(cli.main)
    importlib.reload(server.app)


def test_cli_version_resolves_from_dist_name(only_real_dist):
    import cli.main

    assert importlib.reload(cli.main)._VERSION == FAKE


def test_server_version_resolves_from_dist_name(only_real_dist):
    import server.app

    assert importlib.reload(server.app)._VERSION == FAKE
