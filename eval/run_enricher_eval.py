from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# ruff: noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

from src.backend.Raven_graph import enricher

load_dotenv(REPO_ROOT / ".env")

EVAL_DIR = REPO_ROOT / "eval"
THREADS_DIR = EVAL_DIR / "threads"
TRACE_DIR_NAME = "traces"
DEFAULT_DATASET = EVAL_DIR / "enricher_cases.jsonl"

STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "as",
    "for",
    "from",
    "how",
    "in",
    "of",
    "or",
    "the",
    "to",
    "what",
    "when",
    "why",
    "with",
    "without",
}

CONTROL_LEAK_MARKERS = (
    "system message",
    "developer message",
    "structured output",
    "return json",
    "enricheroutput",
    "ignore previous",
)

OPERATIONAL_MARKERS = (
    "workflow",
    "system",
    "process",
    "implementation",
    "tool",
    "tools",
    "metric",
    "metrics",
    "template",
    "playbook",
    "case study",
    "debugging",
    "example",
    "examples",
    "incident",
    "teardown",
    "postmortem",
    "rollback",
    "mistake",
    "mistakes",
    "failure",
    "fail",
    "fails",
    "tradeoff",
    "tradeoffs",
    "numbers",
)

DEFAULT_FORBIDDEN_KEY_WORDS = {
    "build",
    "case",
    "example",
    "examples",
    "guide",
    "method",
    "study",
    "system",
    "tip",
    "tips",
    "tool",
    "tools",
    "workflow",
}


@dataclass(frozen=True)
class RunOutcome:
    run_index: int
    thread_id: str
    status: str
    trace_path: Path
    production_ready: bool
    error_message: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Raven query-enricher production evals.")
    parser.add_argument(
        "--file", default=str(DEFAULT_DATASET), help="Path to a JSONL file inside eval/."
    )
    parser.add_argument("--mode", choices=("single", "multi"), default="multi")
    parser.add_argument("--workers", type=int, default=None)
    return parser.parse_args()


def resolve_input_file(file_arg: str) -> Path:
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

            if not isinstance(parsed.get("target"), str) or not parsed["target"].strip():
                raise ValueError(f"Line {line_number} must include a non-empty 'target'.")

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


def normalize_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("es") and len(token) > 4 and not token.endswith("ses"):
        return token[:-2]
    if token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> set[str]:
    return {
        normalize_token(token)
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 1 and token not in STOPWORDS
    }


def audit_queries(raw_input: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    target = " ".join(raw_input["target"].split())
    queries = output.get("queries") or []
    if not isinstance(queries, list):
        queries = []
    key_words = output.get("key_words") or []
    if not isinstance(key_words, list):
        key_words = []

    cleaned_queries = [" ".join(str(query).split()) for query in queries]
    query_keys = [query.casefold() for query in cleaned_queries]
    cleaned_key_words = [
        normalize_token(" ".join(str(keyword).casefold().split()))
        for keyword in key_words
        if str(keyword).strip()
    ]
    key_word_tokens = set(cleaned_key_words)
    target_tokens = tokenize(target)
    expected_keywords = [
        normalize_token(str(keyword).casefold())
        for keyword in raw_input.get("expected_keywords", [])
    ]
    required_terms_per_query = [
        normalize_token(str(term).casefold())
        for term in raw_input.get("required_terms_per_query", [])
    ]
    forbidden_query_phrases = [
        " ".join(str(phrase).casefold().split())
        for phrase in raw_input.get("forbidden_query_phrases", [])
    ]
    forbidden_key_words = {
        normalize_token(str(keyword).casefold())
        for keyword in raw_input.get("forbidden_key_words", DEFAULT_FORBIDDEN_KEY_WORDS)
    }
    relevant_count = 0
    for query in cleaned_queries:
        query_tokens = tokenize(query)
        if target_tokens and query_tokens.intersection(target_tokens):
            relevant_count += 1

    relevance_ratio = relevant_count / len(cleaned_queries) if cleaned_queries else 0.0
    marker_hits = sorted(
        {
            marker
            for marker in OPERATIONAL_MARKERS
            if any(marker in query.casefold() for query in cleaned_queries)
        }
    )
    required_marker_count = max(1, min(3, len(cleaned_queries) - 1))

    checks = {
        "exact_target_first": bool(cleaned_queries and cleaned_queries[0] == target),
        "has_queries": bool(cleaned_queries),
        "no_duplicates": len(query_keys) == len(set(query_keys)),
        "no_empty_queries": all(bool(query) for query in cleaned_queries),
        "relevance_ratio_ok": relevance_ratio >= 0.8,
        "expected_keywords_present": all(
            any(keyword in tokenize(query) for query in cleaned_queries)
            for keyword in expected_keywords
        ),
        "has_key_words": bool(cleaned_key_words),
        "no_empty_key_words": len(cleaned_key_words) == len(key_words),
        "key_word_count_ok": 1 <= len(cleaned_key_words) <= 8,
        "key_words_from_target": all(
            keyword in target_tokens
            for keyword in cleaned_key_words
        ),
        "expected_key_words_present": all(
            keyword in key_word_tokens
            for keyword in expected_keywords
        ),
        "forbidden_key_words_absent": not any(
            keyword in forbidden_key_words
            for keyword in cleaned_key_words
        ),
        "required_terms_per_query_present": all(
            all(term in tokenize(query) for term in required_terms_per_query)
            for query in cleaned_queries
        ),
        "forbidden_query_phrases_absent": not any(
            phrase and phrase in query.casefold()
            for phrase in forbidden_query_phrases
            for query in cleaned_queries
        ),
        "operational_specificity_ok": len(marker_hits) >= required_marker_count,
        "no_control_leak": not any(
            marker in query.casefold()
            for marker in CONTROL_LEAK_MARKERS
            for query in cleaned_queries
        ),
    }

    return {
        "production_ready": all(checks.values()),
        "checks": checks,
        "query_count": len(cleaned_queries),
        "relevance_ratio": relevance_ratio,
        "required_marker_count": required_marker_count,
        "operational_markers": marker_hits,
        "key_words": cleaned_key_words,
        "forbidden_key_words": sorted(forbidden_key_words),
        "required_terms_per_query": required_terms_per_query,
        "forbidden_query_phrases": forbidden_query_phrases,
    }


def write_trace(trace: dict[str, Any], thread_id: str, run_index: int) -> Path:
    trace_dir = THREADS_DIR / thread_id / TRACE_DIR_NAME
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"run_{run_index:04d}.json"
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return trace_path


def run_one_input(
    raw_input: dict[str, Any],
    file_path: Path,
    run_index: int,
    thread_id: str,
    mode: str,
) -> RunOutcome:
    timestamp = datetime.now().astimezone().isoformat()
    normalized_input = {"query": " ".join(raw_input["target"].split())}
    trace: dict[str, Any] = {
        "graph_name": "raven_enricher_node",
        "graph_key": "enricher",
        "graph_module": "src.backend.Raven_graph",
        "input_file": str(file_path.relative_to(REPO_ROOT)),
        "mode": mode,
        "run_index": run_index,
        "thread_id": thread_id,
        "timestamp": timestamp,
        "input": serialize_value(raw_input),
        "normalized_input": normalized_input,
        "output": None,
        "audit": None,
        "status": "success",
    }

    try:
        output = enricher(normalized_input)
        audit = audit_queries(raw_input=raw_input, output=output)
        trace["output"] = serialize_value(output)
        trace["audit"] = audit
    except Exception as exc:
        trace["status"] = "error"
        trace["output"] = {
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
        }
        trace["error_traceback"] = traceback.format_exc()

    trace_path = write_trace(trace=trace, thread_id=thread_id, run_index=run_index)
    error_message = None
    production_ready = False

    if trace["status"] == "error":
        error_message = trace["output"]["error_message"]
    else:
        production_ready = bool(trace["audit"]["production_ready"])
        if not production_ready:
            failed = [name for name, passed in trace["audit"]["checks"].items() if not passed]
            error_message = f"failed checks: {', '.join(failed)}"

    return RunOutcome(
        run_index=run_index,
        thread_id=thread_id,
        status=trace["status"],
        trace_path=trace_path,
        production_ready=production_ready,
        error_message=error_message,
    )


def print_outcome(outcome: RunOutcome) -> None:
    relative_trace_path = outcome.trace_path.relative_to(REPO_ROOT)
    if outcome.production_ready:
        print(
            f"[{outcome.run_index:04d}] ready  "
            f"thread={outcome.thread_id} trace={relative_trace_path}"
        )
        return

    print(
        f"[{outcome.run_index:04d}] fail   thread={outcome.thread_id} "
        f"trace={relative_trace_path} reason={outcome.error_message}"
    )


def run_single_mode(inputs: list[dict[str, Any]], file_path: Path) -> list[RunOutcome]:
    shared_thread_id = str(uuid4())
    print(f"Single thread_id: {shared_thread_id}")

    outcomes: list[RunOutcome] = []
    for run_index, raw_input in enumerate(inputs, start=1):
        outcome = run_one_input(
            raw_input=raw_input,
            file_path=file_path,
            run_index=run_index,
            thread_id=shared_thread_id,
            mode="single",
        )
        outcomes.append(outcome)
        print_outcome(outcome)

    return outcomes


def run_multi_mode(
    inputs: list[dict[str, Any]],
    file_path: Path,
    workers: int | None,
) -> list[RunOutcome]:
    max_workers = workers or min(4, len(inputs))
    if max_workers < 1:
        raise ValueError("--workers must be >= 1.")

    print(f"Workers: {max_workers}")

    outcomes: list[RunOutcome] = []
    with ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix="raven-enricher-eval"
    ) as executor:
        future_map = {
            executor.submit(
                run_one_input,
                raw_input,
                file_path,
                run_index,
                str(uuid4()),
                "multi",
            ): run_index
            for run_index, raw_input in enumerate(inputs, start=1)
        }

        for future in as_completed(future_map):
            outcome = future.result()
            outcomes.append(outcome)
            print_outcome(outcome)

    outcomes.sort(key=lambda item: item.run_index)
    return outcomes


def main() -> None:
    args = parse_args()
    file_path = resolve_input_file(args.file)
    inputs = load_jsonl_inputs(file_path)

    THREADS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"File: {file_path.relative_to(REPO_ROOT)}")
    print("Graph: src.backend.Raven_graph.enricher")
    print(f"Mode: {args.mode}")
    print(f"Inputs: {len(inputs)}")

    if args.mode == "single":
        outcomes = run_single_mode(inputs=inputs, file_path=file_path)
    else:
        outcomes = run_multi_mode(inputs=inputs, file_path=file_path, workers=args.workers)

    ready_count = sum(1 for outcome in outcomes if outcome.production_ready)
    failure_count = len(outcomes) - ready_count

    print(f"Production-ready cases: {ready_count}")
    print(f"Failed cases: {failure_count}")

    if failure_count:
        print("Production ready: NO")
        raise SystemExit(1)

    print("Production ready: YES")


if __name__ == "__main__":
    main()
