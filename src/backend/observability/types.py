from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ObservationCaseResult:
    run_index: int
    thread_id: str
    status: str
    production_ready: bool
    input: dict[str, Any]
    output: dict[str, Any] | None
    audit: dict[str, Any] | None
    error_message: str | None = None
    trace_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ObservationResult:
    kind: str
    name: str
    status: str
    production_ready: bool
    thread_id: str
    trace: dict[str, Any]
    cases: list[ObservationCaseResult]
    packet_dir: Path | None = None
    audit_markdown_name: str | None = None
