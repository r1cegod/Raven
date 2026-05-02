from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO_ROOT / "eval"
PACKETS_DIR = EVAL_DIR / "packets"
THREADS_DIR = EVAL_DIR / "threads"
DEFAULT_DB_PATH = REPO_ROOT / "src/backend/data/raven.sqlite"
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def vietnam_now() -> str:
    return datetime.now(VIETNAM_TZ).isoformat()


def to_vietnam_time(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        source = value
    else:
        source = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return source.astimezone(VIETNAM_TZ).strftime("%H:%M:%S, %d %b %Y (Vietnam, UTC+7)")


def local_packet_date() -> str:
    return datetime.now(VIETNAM_TZ).strftime("%d-%b-%Y")


def local_packet_time() -> str:
    return datetime.now(VIETNAM_TZ).strftime("%H:%M:%S")


def slugify(value: str, *, max_length: int = 72) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return (slug or "run")[:max_length].strip("-") or "run"


def resolve_jsonl_file(file_arg: str) -> Path:
    file_path = Path(file_arg)
    resolved = (
        (REPO_ROOT / file_path).resolve() if not file_path.is_absolute() else file_path.resolve()
    )

    if resolved.suffix.lower() != ".jsonl":
        raise ValueError("--file must point to a .jsonl file.")
    if not resolved.is_file():
        raise FileNotFoundError(f"Input file not found: {resolved}")

    try:
        resolved.relative_to(EVAL_DIR)
    except ValueError as exc:
        raise ValueError(f"--file must point to a JSONL file inside {EVAL_DIR}") from exc

    return resolved


def load_jsonl_inputs(file_path: Path) -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []

    with file_path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} in {file_path}") from exc

            if not isinstance(parsed, dict):
                raise ValueError(f"Line {line_number} in {file_path} must be a JSON object.")

            inputs.append(parsed)

    if not inputs:
        raise ValueError(f"No JSON objects found in {file_path}")

    return inputs


def serialize_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return serialize_value(value.model_dump())
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialize_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
