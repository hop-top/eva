# core/config.py
"""EvaConfig — project-level configuration loaded from eva.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class EvaConfig(BaseModel):
    version: str = "1"
    project: str = "eva"
    storage: str = "sqlite"
    otel: str = "noop"
    concurrency: str = "semaphore"
    max_workers: int = 4
    min_score: float = 0.0


_CONFIG_FILENAME = "eva.yaml"

_CONFIG_TEMPLATE = """\
# eva.yaml — project configuration
# version: "1"
# project: eva
# storage: sqlite        # sqlite | postgres | custom plugin
# otel: noop             # noop | stdout | otlp
# concurrency: semaphore # semaphore | thread
# max_workers: 4
# min_score: 0.0
"""


def find_and_load_config(start: Path | None = None) -> EvaConfig:
    """Walk up from *start* (default: cwd) looking for eva.yaml.

    Returns default EvaConfig if none found.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        config_file = candidate / _CONFIG_FILENAME
        if config_file.exists():
            raw: dict[str, Any] = yaml.safe_load(config_file.read_text()) or {}
            return EvaConfig.model_validate(raw)
    return EvaConfig()
