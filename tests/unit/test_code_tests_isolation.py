"""code_tests isolation: model code that misbehaves must not affect the host.

Containment that is platform-specific is asserted where the platform provides
it (macOS: network, filesystem writes/reads, fork; Linux: network when
unprivileged user namespaces are available). Everything else (env scrub,
throwaway cwd, timeout, memory/process watchdog, file size limit) is asserted
on every platform.
"""
import os
import socket
import sys
import threading
import time

import pytest

from core.evaluators import _sandbox
from core.evaluators.code_tests import CodeTestsEvaluator

DARWIN = sys.platform == "darwin"
STATUS = _sandbox.isolation_status()


def fence(code):
    return f"```python\n{code}\n```"


def run(code, tests="pass", **kw):
    kw.setdefault("timeout", 30)  # generous: shared, loaded CI hosts
    return CodeTestsEvaluator(**kw).run_case(fence(code), {"tests": tests})


def test_status_reports_mechanisms():
    assert {"network", "fs_write", "fs_read", "fork", "memory", "mechanism"} <= set(STATUS)
    assert STATUS["memory"] is True  # watchdog is stdlib + ps, every platform
    if DARWIN:
        assert STATUS["network"] and STATUS["fs_write"] and STATUS["fs_read"]


def test_secret_env_not_visible_score_zero(monkeypatch):
    monkeypatch.setenv("EVA_TEST_SECRET", "fake-secret-value")
    s = run("import os\nprint(os.environ['EVA_TEST_SECRET'])")
    assert s.value == 0.0 and "KeyError" in s.reason
    assert "fake-secret-value" not in s.reason


def test_secret_env_not_visible_via_proc_environ_children(monkeypatch):
    monkeypatch.setenv("EVA_TEST_SECRET", "fake-secret-value")
    code = (
        "import os\n"
        "assert not any('fake-secret-value' in v for v in os.environ.values())\n"
        "assert not any(k.startswith('EVA_') for k in os.environ)\n"
    )
    assert run(code).value == 1.0


@pytest.mark.skipif(not STATUS["fs_write"], reason="no filesystem write containment here")
def test_write_outside_workdir_blocked(tmp_path):
    target = tmp_path / "outside.txt"
    s = run(f"open({str(target)!r}, 'w').write('pwned')")
    assert s.value == 0.0
    assert "PermissionError" in s.reason and "sandbox" in s.reason
    assert not target.exists()


@pytest.mark.skipif(not STATUS["fs_write"], reason="no filesystem write containment here")
def test_write_inside_workdir_allowed():
    assert run("open('ok.txt', 'w').write('x')\nassert open('ok.txt').read() == 'x'").value == 1.0


@pytest.mark.skipif(not STATUS["fs_read"], reason="no filesystem read containment here")
def test_read_of_host_file_blocked(tmp_path):
    secret = tmp_path / "host-secret.txt"
    secret.write_text("fake-file-secret")
    s = run(f"print(open({str(secret)!r}).read())")
    assert s.value == 0.0 and "PermissionError" in s.reason
    assert "fake-file-secret" not in s.reason


@pytest.mark.skipif(not STATUS["network"], reason="no network containment here")
def test_network_blocked():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    accepted = []

    def accept():
        srv.settimeout(5)
        try:
            c, _ = srv.accept()
            accepted.append(c)
            c.close()
        except OSError:
            pass

    t = threading.Thread(target=accept)
    t.start()
    try:
        s = run(f"import socket\nsocket.create_connection(('127.0.0.1', {port}), timeout=3)")
    finally:
        t.join()
        srv.close()
    assert s.value == 0.0
    assert not accepted, "sandboxed code reached a host listener"


@pytest.mark.skipif(not STATUS["fork"], reason="no fork containment here")
def test_fork_blocked():
    s = run("import os\nos.fork()")
    assert s.value == 0.0 and "PermissionError" in s.reason


def test_runs_in_throwaway_cwd():
    code = (
        "import os\n"
        "d = os.getcwd()\n"
        "assert os.path.basename(d).startswith('eva-code-'), d\n"
        "assert os.path.realpath(os.environ['HOME']) == os.path.realpath(d)\n"
        "open('leak.txt', 'w').write('x')\n"
    )
    cwd = os.getcwd()
    assert run(code).value == 1.0
    assert not os.path.exists(os.path.join(cwd, "leak.txt"))


def test_workdir_removed_afterwards(monkeypatch):
    seen = []
    orig = _sandbox.run_isolated

    def spy(argv, **kw):
        seen.append(kw["workdir"])
        return orig(argv, **kw)

    monkeypatch.setattr(_sandbox, "run_isolated", spy)
    assert run("import os\nprint(os.getcwd())").value == 1.0
    assert seen and not os.path.exists(seen[0])


def test_infinite_loop_times_out_host_unaffected():
    t0 = time.time()
    s = run("while True:\n    pass", timeout=2)
    assert s.value == 0.0 and "timeout after 2" in s.reason
    assert time.time() - t0 < 20


def test_memory_hog_killed_with_reason():
    code = (
        "chunks = []\n"
        "while True:\n"
        "    chunks.append(b'x' * (32 << 20))\n"
    )
    s = run(code, timeout=60, memory_mb=256)
    assert s.value == 0.0 and "memory limit" in s.reason and "256" in s.reason


def test_oversized_file_write_stopped(tmp_path):
    code = "with open('big.bin', 'wb') as f:\n    f.write(b'x' * (64 << 20))"
    s = run(code, max_file_mb=2)
    assert s.value == 0.0 and "file size limit" in s.reason


def test_runaway_output_bounded():
    s = run("import sys\nwhile True:\n    sys.stdout.write('x' * 65536)", timeout=30, max_file_mb=1)
    assert s.value == 0.0 and "file size limit" in s.reason
    assert len(s.reason) < 5000


def test_process_cap_kills_group():
    r = _sandbox.run_isolated(
        [sys.executable, "-I", "-c",
         "import subprocess, sys, time\n"
         "ps = [subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(60)'])"
         " for _ in range(40)]\n"
         "time.sleep(60)\n"],
        workdir=_mk(),
        timeout=60,
        max_procs=10,
        memory_mb=8192,
        contain=False,
    )
    assert r.killed == "processes"


def test_cpu_limit_is_set_as_backstop():
    r = _sandbox.run_isolated(
        [sys.executable, "-I", "-c",
         "import resource\n"
         "s, h = resource.getrlimit(resource.RLIMIT_CPU)\n"
         "print(s)\n"],
        workdir=_mk(),
        timeout=7,
        contain=False,
    )
    assert r.returncode == 0 and int(r.stdout.strip()) <= 7 + 5


def test_contain_false_runs_plain():
    r = _sandbox.run_isolated(
        [sys.executable, "-I", "-c", "print('hi')"], workdir=_mk(), timeout=30, contain=False
    )
    assert r.stdout.strip() == "hi" and r.killed is None


def _mk():
    import tempfile

    d = tempfile.mkdtemp(prefix="eva-code-")
    return d


NO_LAYER = {
    "mechanism": "none", "network": False, "fs_write": False,
    "fs_read": False, "fork": False, "memory": True,
}
ACTIVE = {**NO_LAYER, "mechanism": "sandbox-exec", "network": True}


@pytest.fixture
def spy_runs(monkeypatch):
    calls = []
    orig = _sandbox.run_isolated

    def spy(argv, **kw):
        calls.append(argv)
        return orig(argv, **kw)

    monkeypatch.setattr(_sandbox, "run_isolated", spy)
    return calls


def test_require_isolation_without_layer_scores_zero_and_does_not_run(monkeypatch, spy_runs):
    monkeypatch.setattr(_sandbox, "isolation_status", lambda: NO_LAYER)
    s = run("print('hi')", require_isolation=True)
    assert s.value == 0.0 and not spy_runs
    assert "require_isolation" in s.reason and "mechanism: none" in s.reason
    assert "network" in s.reason and "fs_write" in s.reason


def test_require_isolation_without_layer_stdio_mode(monkeypatch, spy_runs):
    monkeypatch.setattr(_sandbox, "isolation_status", lambda: NO_LAYER)
    s = CodeTestsEvaluator(require_isolation=True).run_case(
        fence("print(1)"), {"stdio": [{"stdin": "", "expected_stdout": "1\n"}]}
    )
    assert s.value == 0.0 and not spy_runs and "require_isolation" in s.reason


def test_require_isolation_with_layer_runs(monkeypatch, spy_runs):
    monkeypatch.setattr(_sandbox, "isolation_status", lambda: ACTIVE)
    assert run("print('hi')", require_isolation=True).value == 1.0
    assert spy_runs


def test_default_runs_without_layer(monkeypatch, spy_runs):
    monkeypatch.setattr(_sandbox, "isolation_status", lambda: NO_LAYER)
    assert run("print('hi')").value == 1.0 and spy_runs


def test_require_isolation_not_applicable_case_stays_none(monkeypatch):
    monkeypatch.setattr(_sandbox, "isolation_status", lambda: NO_LAYER)
    assert CodeTestsEvaluator(require_isolation=True).run_case(fence("x=1"), {}) is None


def test_factory_passes_require_isolation():
    from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES

    ev = BUILTIN_EVALUATOR_FACTORIES["code_tests"]({"require_isolation": True}, None)
    assert ev.require_isolation is True


def test_warning_includes_status(monkeypatch, caplog):
    monkeypatch.setattr(_sandbox, "isolation_status", lambda: NO_LAYER)
    monkeypatch.setattr(_sandbox._warn_uncontained_once, "done", False, raising=False)
    with caplog.at_level("WARNING"):
        _sandbox._warn_uncontained_once()
    assert "mechanism" in caplog.text and "fs_write" in caplog.text
