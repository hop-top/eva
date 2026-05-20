# tests/e2e/test_annotation_commands.py
"""E2E tests for `eva annotate` and `eva review queue` CLI commands — T-0142/T-0143/T-0144."""
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.e2e


def run_eva(*args: str, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli.main"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_invocation(db_path: str) -> str:
    """Insert a minimal InvocationRecord directly so FK constraints are met."""
    from core.storage import SqliteStorage
    from core.models import Invocation, EvaluatorResult

    storage = SqliteStorage(db_url=f"sqlite:///{db_path}")
    inv_id = str(uuid.uuid4())
    invocation = Invocation(
        invocation_id=inv_id,
        source="offline_run",
        target="http://localhost:9999",
        status="fail",
        started_at=datetime.now(tz=timezone.utc),
    )
    storage.save_invocation(invocation, [], [])
    return inv_id


def _seed_invocation_with_failure(db_path: str) -> str:
    """Insert an invocation plus a failing EvaluatorResult."""
    from core.storage import SqliteStorage
    from core.models import Invocation, EvaluatorResult

    storage = SqliteStorage(db_url=f"sqlite:///{db_path}")
    inv_id = str(uuid.uuid4())
    invocation = Invocation(
        invocation_id=inv_id,
        source="offline_run",
        target="http://localhost:9999",
        status="fail",
        started_at=datetime.now(tz=timezone.utc),
    )
    er = EvaluatorResult(
        evaluator_result_id=str(uuid.uuid4()),
        invocation_id=inv_id,
        evaluator="my_check",
        score_value=0.0,
        passed=False,
    )
    storage.save_invocation(invocation, [er], [])
    return inv_id


# ---------------------------------------------------------------------------
# annotate add
# ---------------------------------------------------------------------------

def test_annotate_add_help_exits_zero():
    result = run_eva("annotate", "add", "--help")
    assert result.returncode == 0
    assert "invocation" in result.stdout.lower()


def test_annotate_add_persists_annotation(tmp_path):
    """annotate add stores annotation; annotate list retrieves it."""
    db = str(tmp_path / "eva.db")
    inv_id = _seed_invocation(db)

    result = run_eva(
        "annotate", "add",
        "--invocation", inv_id,
        "--label", "correct",
        "--score", "0.9",
        "--notes", "looks good",
        "--reviewer", "tester",
        "--db", db,
    )
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "saved" in combined.lower() or inv_id[:8] in combined

    # Verify via storage API
    from core.storage import SqliteStorage
    storage = SqliteStorage(db_url=f"sqlite:///{db}")
    annotations = storage.list_annotations(inv_id)
    assert len(annotations) == 1
    ann = annotations[0]
    assert ann.label == "correct"
    assert ann.score == pytest.approx(0.9)
    assert ann.notes == "looks good"
    assert ann.reviewer == "tester"
    assert ann.invocation_id == inv_id


def test_annotate_add_minimal_fields(tmp_path):
    """annotate add with only required field (invocation) succeeds."""
    db = str(tmp_path / "eva.db")
    inv_id = _seed_invocation(db)

    result = run_eva(
        "annotate", "add",
        "--invocation", inv_id,
        "--db", db,
    )
    assert result.returncode == 0, result.stderr

    from core.storage import SqliteStorage
    storage = SqliteStorage(db_url=f"sqlite:///{db}")
    annotations = storage.list_annotations(inv_id)
    assert len(annotations) == 1
    assert annotations[0].label is None
    assert annotations[0].score is None


# ---------------------------------------------------------------------------
# annotate list
# ---------------------------------------------------------------------------

def test_annotate_list_help_exits_zero():
    result = run_eva("annotate", "list", "--help")
    assert result.returncode == 0
    assert "invocation" in result.stdout.lower()


def test_annotate_list_retrieves_annotation(tmp_path):
    """annotate list shows the annotation added by annotate add."""
    db = str(tmp_path / "eva.db")
    inv_id = _seed_invocation(db)

    run_eva(
        "annotate", "add",
        "--invocation", inv_id,
        "--label", "wrong",
        "--score", "0.1",
        "--reviewer", "alice",
        "--db", db,
    )

    result = run_eva("annotate", "list", "--invocation", inv_id, "--db", db)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "wrong" in combined
    assert "alice" in combined


def test_annotate_list_empty(tmp_path):
    """annotate list on invocation with no annotations prints a notice."""
    db = str(tmp_path / "eva.db")
    inv_id = _seed_invocation(db)

    result = run_eva("annotate", "list", "--invocation", inv_id, "--db", db)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "no annotation" in combined.lower() or inv_id in combined


# ---------------------------------------------------------------------------
# review queue
# ---------------------------------------------------------------------------

def test_review_queue_help_exits_zero():
    result = run_eva("review", "queue", "--help")
    assert result.returncode == 0
    assert "failed" in result.stdout.lower() or "help" in result.stdout.lower()


def test_review_queue_empty_db(tmp_path):
    """Empty DB → exit 0, 'queue is empty' message."""
    db = str(tmp_path / "eva.db")
    # Create the DB schema without any data
    from core.storage import SqliteStorage
    SqliteStorage(db_url=f"sqlite:///{db}")

    result = run_eva("review", "queue", "--db", db)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "empty" in combined.lower()


def test_review_queue_shows_failed_invocations(tmp_path):
    """Failed invocation appears in the review queue."""
    db = str(tmp_path / "eva.db")
    inv_id = _seed_invocation_with_failure(db)

    result = run_eva("review", "queue", "--db", db)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert inv_id[:12] in combined or "fail" in combined.lower()


def test_review_queue_failed_only_flag(tmp_path):
    """--failed-only flag limits results to invocations with failing evaluators."""
    db = str(tmp_path / "eva.db")
    inv_id = _seed_invocation_with_failure(db)

    result = run_eva("review", "queue", "--failed-only", "--db", db)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert inv_id[:12] in combined or "fail" in combined.lower()


def test_review_queue_evaluator_vs_human_comparison(tmp_path):
    """Review queue shows both evaluator score and human label when both exist."""
    db = str(tmp_path / "eva.db")
    inv_id = _seed_invocation_with_failure(db)

    # Add human annotation
    run_eva(
        "annotate", "add",
        "--invocation", inv_id,
        "--label", "correct",
        "--score", "1.0",
        "--reviewer", "human",
        "--db", db,
    )

    result = run_eva("review", "queue", "--db", db)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    # Evaluator score (0.0 / fail) and human label (correct) both visible
    assert "0.00" in combined or "fail" in combined.lower()
    assert "correct" in combined or "1.00" in combined
