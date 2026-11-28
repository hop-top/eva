# core/evaluators/_sandbox.py
"""Best-effort containment for running model-written code in a subprocess.

Layers (see ``isolation_status()`` for what is active on this host):

- all platforms: own process group (killed on exit), caller-provided
  throwaway cwd, scrubbed environment, ``RLIMIT_CPU`` / ``RLIMIT_FSIZE`` /
  ``RLIMIT_CORE`` applied by a launcher before exec, stdout/stderr/stdin on
  files (parent memory stays bounded), wall-clock timeout, and a parent-side
  watchdog that polls ``ps`` and SIGKILLs the group above a resident-memory
  or process-count cap
- macOS: ``sandbox-exec`` profile denying network, process fork, file
  writes outside the workdir and file-content reads under user/temp roots
- Linux: ``unshare --user --map-root-user --net`` (no network) when
  unprivileged user namespaces are permitted

NOT a security boundary against kernel/sandbox bugs. Linux has no
filesystem containment here. Stdlib only; no root, container or extra
package needed.
"""
from __future__ import annotations

import functools
import logging
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

POLL_SECONDS = 0.25
_OUTPUT_CAP_NOTE = "file size limit"

# Read-denied roots on macOS (content only: metadata stays so path
# resolution works). The interpreter prefixes and the workdir are re-allowed.
_DARWIN_READ_DENY = (
    "/Users",
    "/Volumes",
    "/private/var/folders",
    "/private/tmp",
    "/private/var/tmp",
)

_LAUNCH = (
    "import os, sys, resource\n"
    "cpu, fsz = int(sys.argv[1]), int(sys.argv[2])\n"
    "for r, v in ((resource.RLIMIT_CPU, cpu), (resource.RLIMIT_FSIZE, fsz),\n"
    "             (resource.RLIMIT_CORE, 0)):\n"
    "    try:\n"
    "        resource.setrlimit(r, (v, v))\n"
    "    except (ValueError, OSError):\n"
    "        pass\n"
    "os.execv(sys.argv[3], sys.argv[3:])\n"
)


@dataclass
class RunResult:
    returncode: int | None
    stdout: str
    stderr: str
    killed: str | None  # None | "timeout" | "memory" | "processes"
    contained: bool  # an OS sandbox layer wrapped this run


def _q(path: str) -> str:
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _real(p: str) -> str:
    return os.path.realpath(p)


@functools.lru_cache(maxsize=1)
def _darwin_sandbox_ok() -> bool:
    exe = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
    if not os.path.exists(exe):
        return False
    try:
        r = subprocess.run(
            [exe, "-p", "(version 1)(allow default)(deny network*)", "/usr/bin/true"],
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


@functools.lru_cache(maxsize=1)
def _linux_netns_ok() -> bool:
    exe = shutil.which("unshare")
    if not exe:
        return False
    try:
        r = subprocess.run(
            [exe, "--user", "--map-root-user", "--net", "/bin/true"],
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def isolation_status() -> dict:
    """What containment is active on this host (probed once, cached)."""
    darwin = sys.platform == "darwin" and _darwin_sandbox_ok()
    linux = sys.platform.startswith("linux") and _linux_netns_ok()
    return {
        "mechanism": "sandbox-exec" if darwin else "unshare" if linux else "none",
        "network": darwin or linux,
        "fs_write": darwin,
        "fs_read": darwin,
        "fork": darwin,
        "memory": True,  # parent-side watchdog, every platform
    }


def _warn_uncontained_once() -> None:
    if _warn_uncontained_once.done:  # type: ignore[attr-defined]
        return
    _warn_uncontained_once.done = True  # type: ignore[attr-defined]
    log.warning(
        "code_tests: no OS sandbox available on this host (%s); model code runs "
        "with process/env/limit isolation only. isolation_status: %s. "
        "Set require_isolation: true to refuse to run instead.",
        sys.platform,
        isolation_status(),
    )


_warn_uncontained_once.done = False  # type: ignore[attr-defined]


def _darwin_profile(workdir: str) -> str:
    work = _real(workdir)
    allow_read = {work}
    for p in (sys.prefix, sys.base_prefix, sys.exec_prefix, sys.executable):
        allow_read.add(_real(p))
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny process-fork)",
        "(deny file-write*)",
        f"(allow file-write* (subpath {_q(work)}) (literal \"/dev/null\"))",
    ]
    for root in _DARWIN_READ_DENY:
        lines.append(f"(deny file-read-data (subpath {_q(root)}))")
    home = os.path.expanduser("~")
    if home and not home.startswith(_DARWIN_READ_DENY):
        lines.append(f"(deny file-read-data (subpath {_q(_real(home))}))")
    for p in sorted(allow_read):
        lines.append(f"(allow file-read-data (subpath {_q(p)}))")
    return "\n".join(lines)


def _wrap(argv: list[str], workdir: str, contain: bool) -> tuple[list[str], bool]:
    if not contain:
        return argv, False
    if sys.platform == "darwin" and _darwin_sandbox_ok():
        exe = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        return [exe, "-p", _darwin_profile(workdir), *argv], True
    if sys.platform.startswith("linux") and _linux_netns_ok():
        exe = shutil.which("unshare") or "unshare"
        return [exe, "--user", "--map-root-user", "--net", *argv], True
    _warn_uncontained_once()
    return argv, False


def _group_usage(pgid: int) -> tuple[int, int]:
    """(resident KiB, process count) of process group ``pgid``."""
    try:
        out = subprocess.run(
            ["ps", "-axo", "pgid=,rss="], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0, 0
    rss = n = 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == str(pgid):
            try:
                rss += int(parts[1])
            except ValueError:
                continue
            n += 1
    return rss, n


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _read(path: str, limit: int) -> str:
    with open(path, "rb") as f:
        return f.read(limit).decode("utf-8", errors="replace")


def run_isolated(
    argv: list[str],
    *,
    workdir: str,
    timeout: float,
    stdin_data: str | None = None,
    memory_mb: int = 512,
    max_file_mb: int = 16,
    max_procs: int = 64,
    contain: bool = True,
) -> RunResult:
    """Run ``argv`` in ``workdir`` with the layers described in the module doc."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": workdir,
        "TMPDIR": workdir,
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    fsize = max_file_mb << 20
    cpu = math.ceil(timeout) + 2
    launch = [sys.executable, "-I", "-c", _LAUNCH, str(cpu), str(fsize), *argv]
    full, contained = _wrap(launch, workdir, contain)

    ctl = tempfile.mkdtemp(prefix="eva-io-")  # parent-owned, outside workdir
    try:
        in_path = os.path.join(ctl, "in")
        out_path = os.path.join(ctl, "out")
        err_path = os.path.join(ctl, "err")
        with open(in_path, "w") as f:
            f.write(stdin_data or "")
        with open(in_path, "rb") as fin, open(out_path, "wb") as fout, open(
            err_path, "wb"
        ) as ferr:
            proc = subprocess.Popen(
                full,
                cwd=workdir,
                env=env,
                stdin=fin,
                stdout=fout,
                stderr=ferr,
                start_new_session=True,
            )
        killed: str | None = None
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    proc.wait(timeout=POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    pass
                rss_kib, nproc = _group_usage(proc.pid)
                if rss_kib > memory_mb * 1024:
                    killed = "memory"
                elif nproc > max_procs:
                    killed = "processes"
                elif time.monotonic() >= deadline:
                    killed = "timeout"
                if killed:
                    _kill_group(proc.pid)
                    proc.wait()
                    break
        finally:
            _kill_group(proc.pid)  # stray children of a finished run
        limit = (max_file_mb << 20) + 1
        return RunResult(
            returncode=proc.returncode,
            stdout=_read(out_path, limit),
            stderr=_read(err_path, limit),
            killed=killed,
            contained=contained,
        )
    finally:
        shutil.rmtree(ctl, ignore_errors=True)
