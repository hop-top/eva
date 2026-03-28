# core/config.py
"""EvaConfig — project-level configuration loaded from eva.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ObservabilityConfig(BaseModel):
    """Observability sub-config nested under ``observability:`` in eva.yaml."""

    sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of requests for which full artifact writes occur (0.0-1.0).",
    )
    redaction_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns; matches in artifact content are replaced with [REDACTED].",
    )
    artifact_max_size_bytes: int = Field(
        default=0,
        ge=0,
        description="Max artifact payload size in bytes before truncation. 0 = unlimited.",
    )
    retention_ttl_days: int = Field(
        default=0,
        ge=0,
        description="Delete artifact rows older than this many days. 0 = keep forever.",
    )


class EvaConfig(BaseModel):
    version: str = "1"
    project: str = "eva"
    storage: str = "sqlite"
    otel: str = "noop"
    concurrency: str = "semaphore"
    max_workers: int = 4
    min_score: float = 0.0
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)


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
# observability:
#   sample_rate: 1.0             # 0.0-1.0; fraction of requests with artifact writes
#   redaction_patterns: []       # regex list; matches replaced with [REDACTED]
#   artifact_max_size_bytes: 0   # 0 = unlimited
#   retention_ttl_days: 0        # 0 = keep forever
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
