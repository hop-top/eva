# core/nltk_data.py
"""nltk data the ``ifeval_check`` evaluator needs, and its explicit fetch.

Nothing here downloads implicitly: only :func:`fetch` (``eva data fetch``)
touches the network. The evaluator only calls :func:`missing`.

Data location, in priority order for a fetch: ``--dir``, the first entry of
``NLTK_DATA`` if set, else ``<XDG_DATA_HOME or ~/.local/share>/eva/nltk_data``.
Lookup at evaluation time covers every ``NLTK_DATA`` entry, nltk's own search
path and the default directory above.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterable

# (path relative to an nltk data dir, nltk downloader id)
REQUIRED: tuple[tuple[str, str], ...] = (
    ("tokenizers/punkt_tab", "punkt_tab"),
    ("corpora/stopwords", "stopwords"),
    ("taggers/averaged_perceptron_tagger_eng", "averaged_perceptron_tagger_eng"),
)

FETCH_COMMAND = "eva data fetch"


def default_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "eva" / "nltk_data"


def _env_dirs() -> list[Path]:
    raw = os.environ.get("NLTK_DATA", "")
    return [Path(p) for p in raw.split(os.pathsep) if p]


def target_dir(override: str | os.PathLike | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    env = _env_dirs()
    return env[0].expanduser() if env else default_dir()


def search_dirs(extra: Iterable[str | os.PathLike] = ()) -> list[Path]:
    dirs = [*_env_dirs(), *(Path(p) for p in extra), default_dir()]
    seen: list[Path] = []
    for d in dirs:
        d = d.expanduser()
        if d not in seen:
            seen.append(d)
    return seen


def _present(dirs: Iterable[Path], rel: str) -> bool:
    return any((d / rel).exists() or (d / f"{rel}.zip").exists() for d in dirs)


def missing(dirs: Iterable[Path] | None = None) -> list[str]:
    """Downloader ids of required resources absent from ``dirs``."""
    dirs = list(dirs) if dirs is not None else search_dirs()
    return [rid for rel, rid in REQUIRED if not _present(dirs, rel)]


def _nltk_download(resource: str, download_dir: str) -> bool:
    import nltk  # lazy: needs the ``ifeval`` extra

    return bool(nltk.download(resource, download_dir=download_dir, quiet=True))


def fetch(
    directory: str | os.PathLike | None = None,
    dry_run: bool = False,
    downloader: Callable[[str, str], bool] | None = None,
) -> dict:
    """Fetch the missing required resources into ``directory``.

    Returns ``{"dir", "dry_run", "ok", "resources": [{"id", "status"}]}``;
    status is ``present``, ``would_fetch`` (dry run), ``fetched`` or ``failed``.
    Resources already present in the target directory are not fetched again.
    """
    target = target_dir(directory)
    download = downloader or _nltk_download
    out: list[dict] = []
    ok = True
    for rel, rid in REQUIRED:
        if _present([target], rel):
            out.append({"id": rid, "status": "present"})
        elif dry_run:
            out.append({"id": rid, "status": "would_fetch"})
        else:
            target.mkdir(parents=True, exist_ok=True)
            try:
                done = download(rid, str(target)) and _present([target], rel)
            except Exception:  # network / unzip errors: report, keep going
                done = False
            out.append({"id": rid, "status": "fetched" if done else "failed"})
            ok = ok and done
    return {"dir": str(target), "dry_run": dry_run, "ok": ok, "resources": out}
