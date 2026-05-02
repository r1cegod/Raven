from __future__ import annotations

import os
import re
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.backend.data.prompt.ranker_tier1 import RANKER_TIER_1, TIER_1
from src.backend.data.prompt.ranker_tier1_final import (
    PACKET,
    RANKER_TIER1_FINAL_INPUT,
    RANKER_TIER1_FINAL_PROMPT,
)
from src.backend.observability.common import (
    REPO_ROOT,
    load_jsonl_inputs,
    repo_relative,
    resolve_jsonl_file,
    serialize_value,
    utc_now,
)
from src.backend.observability.types import ObservationCaseResult, ObservationResult


load_dotenv(REPO_ROOT / ".env")

PROMPT_TOKEN_LIMIT = 500
ALLOWED_TIER1_DECISIONS = {"keep", "throw_out"}
ALLOWED_FINAL_LABELS = {"maybe", "click", "must_click"}

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

ENRICHER_CONTROL_LEAK_MARKERS = (
    "system message",
    "developer message",
    "structured output",
    "return json",
    "enricheroutput",
    "ignore previous",
)

RANKER_CONTROL_LEAK_MARKERS = (
    "system prompt",
    "system message",
    "developer message",
    "structured output",
    "return json",
    "output schema",
    "rankertier1",
    "ignore previous",
)

FINAL_CONTROL_LEAK_MARKERS = (
    "system prompt",
    "system message",
    "developer message",
    "structured output",
    "output schema",
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


class RankerTier1Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    final_decision: Literal["keep", "throw_out"]
    reasoning: str = Field(max_length=360)


class Tier1FinalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: int
    sexy_label: Literal["maybe", "click", "must_click"]
    reason: str = Field(max_length=220)


class Tier1FinalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: list[Tier1FinalDecision]


@dataclass(frozen=True)
class DatasetOptions:
    suite: str
    file: str
    mode: str = "multi"
    workers: int | None = None
    model: str | None = None
    temperature: float = 0.7


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


def validate_enricher_input(raw_input: dict[str, Any], line_label: str) -> None:
    if not get_request(raw_input):
        raise ValueError(f"{line_label} must include a non-empty 'request'.")


def validate_ranker_input(raw_input: dict[str, Any], line_label: str) -> None:
    for key in ("id", "title", "description"):
        if key not in raw_input:
            raise ValueError(f"{line_label} missing required key: {key}")
    if not raw_input.get("allowed_decisions"):
        raise ValueError(f"{line_label} missing required key: allowed_decisions")
    if not get_request(raw_input):
        raise ValueError(f"{line_label} must include a non-empty 'request'.")


def validate_final_input(raw_input: dict[str, Any], line_label: str) -> None:
    for key in ("id", "candidates", "expected_labels"):
        if key not in raw_input:
            raise ValueError(f"{line_label} missing required key: {key}")
    if not get_request(raw_input):
        raise ValueError(f"{line_label} must include a non-empty 'request'.")


def get_request(raw_input: dict[str, Any]) -> str:
    return " ".join(str(raw_input.get("request", "")).split())


def load_validated_inputs(file_path: Path, suite: str) -> list[dict[str, Any]]:
    inputs = load_jsonl_inputs(file_path)
    validators = {
        "enricher": validate_enricher_input,
        "ranker_tier1": validate_ranker_input,
        "ranker_tier1_final": validate_final_input,
    }
    validator = validators[suite]
    for index, raw_input in enumerate(inputs, start=1):
        validator(raw_input, f"Line {index}")
    return inputs


def audit_enricher(raw_input: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    request = get_request(raw_input)
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
    request_tokens = tokenize(request)
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
        if request_tokens and query_tokens.intersection(request_tokens):
            relevant_count += 1

    relevance_ratio = relevant_count / len(cleaned_queries) if cleaned_queries else 0.0
    marker_hits = sorted(
        {
            marker
            for marker in OPERATIONAL_MARKERS
            if any(marker in query.casefold() for query in cleaned_queries)
        }
    )
    required_marker_count = int(
        raw_input.get("min_operational_marker_count", max(1, min(3, len(cleaned_queries) - 1)))
    )

    checks = {
        "has_queries": bool(cleaned_queries),
        "no_duplicates": len(query_keys) == len(set(query_keys)),
        "no_empty_queries": all(bool(query) for query in cleaned_queries),
        "query_count_ok": 1 <= len(cleaned_queries) <= 4,
        "relevance_ratio_ok": relevance_ratio >= 0.8,
        "expected_keywords_present": all(
            any(keyword in tokenize(query) for query in cleaned_queries)
            for keyword in expected_keywords
        ),
        "has_key_words": bool(cleaned_key_words),
        "no_empty_key_words": len(cleaned_key_words) == len(key_words),
        "key_word_count_ok": 1 <= len(cleaned_key_words) <= 8,
        "key_words_from_request": all(
            keyword in request_tokens for keyword in cleaned_key_words
        ),
        "expected_key_words_present": all(
            keyword in key_word_tokens for keyword in expected_keywords
        ),
        "forbidden_key_words_absent": not any(
            keyword in forbidden_key_words for keyword in cleaned_key_words
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
            for marker in ENRICHER_CONTROL_LEAK_MARKERS
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


def audit_ranker(raw_input: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    decision = str(output.get("final_decision", "")).casefold().strip()
    allowed_decisions = allowed_tier1_decisions(raw_input)
    reasoning = str(output.get("reasoning", ""))

    checks = {
        "valid_decision": decision in ALLOWED_TIER1_DECISIONS,
        "expected_decision": decision in allowed_decisions,
        "reasoning_nonempty": bool(reasoning.strip()),
        "no_control_leak": not any(
            marker in reasoning.casefold() for marker in RANKER_CONTROL_LEAK_MARKERS
        ),
    }
    return {
        "production_ready": all(checks.values()),
        "checks": checks,
        "normalized_decision": decision,
    }


def audit_final(raw_input: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expected = {str(key): value for key, value in raw_input["expected_labels"].items()}
    input_ids = {str(candidate["id"]) for candidate in raw_input["candidates"]}
    decisions = output.get("decisions") or []
    by_id = {str(decision.get("candidate_id")): decision for decision in decisions}
    reason_fields = [str(decision.get("reason", "")) for decision in decisions]

    checks = {
        "all_ids_present_once": len(decisions) == len(input_ids) and set(by_id) == input_ids,
        "valid_labels_only": all(
            decision.get("sexy_label") in ALLOWED_FINAL_LABELS for decision in decisions
        ),
        "expected_labels_match": all(
            label_matches(by_id.get(candidate_id, {}).get("sexy_label"), expected_label)
            for candidate_id, expected_label in expected.items()
        ),
        "reasons_nonempty": all(reason.strip() for reason in reason_fields),
        "no_control_leak": not any(
            marker in reason.casefold()
            for marker in FINAL_CONTROL_LEAK_MARKERS
            for reason in reason_fields
        ),
    }
    return {
        "production_ready": all(checks.values()),
        "checks": checks,
        "decisions_by_id": by_id,
    }


def label_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return actual in {str(item) for item in expected}
    return actual == expected


def allowed_tier1_decisions(raw_input: dict[str, Any]) -> set[str]:
    return {str(item) for item in raw_input["allowed_decisions"]}


def count_prompt_tokens(text: str) -> int:
    try:
        import tiktoken

        encoder = tiktoken.encoding_for_model("gpt-4o")
        return len(encoder.encode(text))
    except Exception:  # noqa: BLE001
        return len(text.split())


def make_tier1_final_packet(candidates: list[dict[str, Any]]) -> str:
    packet_blocks = []
    for candidate in candidates:
        packet_blocks.append(
            PACKET.format(
                candidate_id=candidate["id"],
                query=candidate.get("query", ""),
                final_decision=candidate.get("final_decision") or "",
                title=candidate.get("title", ""),
                tier1_reasoning=candidate.get("tier1_reasoning") or candidate.get("final_verdict", ""),
                published_at=candidate.get("published_at", ""),
                view_count=candidate.get("view_count", 0),
            )
        )
    return "\n".join(packet_blocks)


def run_enricher_case(
    raw_input: dict[str, Any],
    file_path: Path,
    run_index: int,
    thread_id: str,
    mode: str,
) -> ObservationCaseResult:
    from src.backend.youtube_ranker_tier1 import enricher

    normalized_input = {"request": get_request(raw_input)}
    try:
        output = serialize_value(enricher(normalized_input))
        audit = audit_enricher(raw_input=raw_input, output=output)
        status = "success"
        production_ready = bool(audit["production_ready"])
        error_message = None
        if not production_ready:
            failed = [name for name, passed in audit["checks"].items() if not passed]
            error_message = f"failed checks: {', '.join(failed)}"
    except Exception as exc:  # noqa: BLE001
        output = {"error_type": exc.__class__.__name__, "error_message": str(exc)}
        audit = None
        status = "error"
        production_ready = False
        error_message = str(exc)

    return ObservationCaseResult(
        run_index=run_index,
        thread_id=thread_id,
        status=status,
        production_ready=production_ready,
        input=raw_input,
        output=output,
        audit=audit,
        error_message=error_message,
        trace_name=f"run_{run_index:04d}.json",
        extra={
            "graph_name": "raven_enricher_node",
            "graph_key": "enricher",
            "graph_module": "src.backend.Raven_graph",
            "mode": mode,
            "normalized_input": normalized_input,
            "dataset": repo_relative(file_path),
            "traceback": traceback.format_exc() if status == "error" else None,
        },
    )


def run_ranker_case(
    raw_input: dict[str, Any],
    ranker_llm: Any,
    file_path: Path,
    run_index: int,
    thread_id: str,
) -> ObservationCaseResult:
    try:
        response = ranker_llm.invoke(
            [
                SystemMessage(RANKER_TIER_1),
                HumanMessage(
                    TIER_1.format(
                        request=get_request(raw_input),
                        title=raw_input["title"],
                        description=raw_input["description"],
                    )
                ),
            ]
        )
        output = serialize_value(response)
        audit = audit_ranker(raw_input, output)
        status = "passed" if audit["production_ready"] else "failed"
        production_ready = bool(audit["production_ready"])
        error_message = None
    except Exception as exc:  # noqa: BLE001
        output = {"error": str(exc)}
        audit = None
        status = "error"
        production_ready = False
        error_message = str(exc)

    return ObservationCaseResult(
        run_index=run_index,
        thread_id=thread_id,
        status=status,
        production_ready=production_ready,
        input=raw_input,
        output=output,
        audit=audit,
        error_message=error_message,
        trace_name=f"ranker_tier1_run_{run_index:04d}.json",
        extra={
            "dataset": repo_relative(file_path),
            "traceback": traceback.format_exc() if status == "error" else None,
        },
    )


def run_final_case(
    raw_input: dict[str, Any],
    tier1_final_llm: Any,
    file_path: Path,
    run_index: int,
    thread_id: str,
) -> ObservationCaseResult:
    candidate_packet = make_tier1_final_packet(raw_input["candidates"])
    try:
        response = tier1_final_llm.invoke(
            [
                SystemMessage(RANKER_TIER1_FINAL_PROMPT),
                HumanMessage(
                    RANKER_TIER1_FINAL_INPUT.format(
                        request=get_request(raw_input),
                        candidate_packet=candidate_packet,
                    )
                ),
            ]
        )
        output = serialize_value(response)
        audit = audit_final(raw_input, output)
        status = "passed" if audit["production_ready"] else "failed"
        production_ready = bool(audit["production_ready"])
        error_message = None
    except Exception as exc:  # noqa: BLE001
        output = {"error": str(exc)}
        audit = None
        status = "error"
        production_ready = False
        error_message = str(exc)

    return ObservationCaseResult(
        run_index=run_index,
        thread_id=thread_id,
        status=status,
        production_ready=production_ready,
        input=raw_input,
        output=output,
        audit=audit,
        error_message=error_message,
        trace_name=f"ranker_tier1_final_run_{run_index:04d}.json",
        extra={
            "dataset": repo_relative(file_path),
            "candidate_packet": candidate_packet,
            "traceback": traceback.format_exc() if status == "error" else None,
        },
    )


def run_enricher_dataset(file_path: Path, options: DatasetOptions) -> list[ObservationCaseResult]:
    inputs = load_validated_inputs(file_path, "enricher")
    if options.mode == "single":
        thread_id = str(uuid4())
        print(f"Single thread_id: {thread_id}")
        return [
            run_enricher_case(raw_input, file_path, index, thread_id, "single")
            for index, raw_input in enumerate(inputs, start=1)
        ]

    max_workers = options.workers or min(4, len(inputs))
    if max_workers < 1:
        raise ValueError("--workers must be >= 1.")
    print(f"Workers: {max_workers}")
    outcomes: list[ObservationCaseResult] = []
    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="raven-enricher-eval",
    ) as executor:
        future_map = {
            executor.submit(
                run_enricher_case,
                raw_input,
                file_path,
                run_index,
                str(uuid4()),
                "multi",
            ): run_index
            for run_index, raw_input in enumerate(inputs, start=1)
        }
        for future in as_completed(future_map):
            outcomes.append(future.result())
    outcomes.sort(key=lambda item: item.run_index)
    return outcomes


def run_ranker_dataset(file_path: Path, options: DatasetOptions) -> list[ObservationCaseResult]:
    inputs = load_validated_inputs(file_path, "ranker_tier1")
    prompt_tokens = count_prompt_tokens(RANKER_TIER_1)
    if prompt_tokens >= PROMPT_TOKEN_LIMIT:
        raise RuntimeError(
            f"RANKER_TIER_1 is {prompt_tokens} tokens; must be < {PROMPT_TOKEN_LIMIT}."
        )
    api_key = os.environ.get("LOW_LLM_KEY") or os.environ.get("ENRICHER_DEV_KEY")
    if not api_key:
        raise RuntimeError("LOW_LLM_KEY or ENRICHER_DEV_KEY is required for ranker eval.")

    llm = ChatOpenAI(
        api_key=SecretStr(api_key),
        model=options.model or "gpt-5.4-mini",
        temperature=options.temperature,
        max_retries=3,
    )
    ranker_llm = llm.with_structured_output(RankerTier1Output)
    thread_id = str(uuid4())
    outcomes = [
        run_ranker_case(raw_input, ranker_llm, file_path, index, thread_id)
        for index, raw_input in enumerate(inputs, start=1)
    ]
    for outcome in outcomes:
        outcome.extra["prompt_tokens"] = prompt_tokens
        outcome.extra["prompt_token_limit"] = PROMPT_TOKEN_LIMIT
    return outcomes


def run_final_dataset(file_path: Path, options: DatasetOptions) -> list[ObservationCaseResult]:
    inputs = load_validated_inputs(file_path, "ranker_tier1_final")
    api_key = os.environ.get("HIGH_LLM_KEY")
    if not api_key:
        raise RuntimeError("HIGH_LLM_KEY is required for Tier 1 final ranker eval.")

    model = options.model or os.getenv(
        "RANKER_TIER1_FINAL_MODEL",
        os.getenv("RANKER_FINAL_MODEL", "gpt-5.4"),
    )
    llm = ChatOpenAI(
        api_key=SecretStr(api_key),
        model=model,
        temperature=options.temperature,
        max_retries=3,
    )
    tier1_final_llm = llm.with_structured_output(Tier1FinalOutput)
    thread_id = str(uuid4())
    return [
        run_final_case(raw_input, tier1_final_llm, file_path, index, thread_id)
        for index, raw_input in enumerate(inputs, start=1)
    ]


def run_dataset(options: DatasetOptions) -> ObservationResult:
    if options.suite not in {"enricher", "ranker_tier1", "ranker_tier1_final"}:
        raise ValueError(f"Unknown suite: {options.suite}")

    file_path = resolve_jsonl_file(options.file)
    runners = {
        "enricher": run_enricher_dataset,
        "ranker_tier1": run_ranker_dataset,
        "ranker_tier1_final": run_final_dataset,
    }
    cases = runners[options.suite](file_path, options)
    passed = sum(1 for outcome in cases if outcome.production_ready)
    production_ready = passed == len(cases)
    thread_id = cases[0].thread_id if cases else str(uuid4())
    prompt_tokens = next(
        (case.extra.get("prompt_tokens") for case in cases if "prompt_tokens" in case.extra),
        None,
    )

    trace = {
        "kind": "dataset",
        "suite": options.suite,
        "dataset": repo_relative(file_path),
        "thread_id": thread_id,
        "started_at": utc_now(),
        "status": "passed" if production_ready else "failed",
        "prompt_tokens": prompt_tokens,
        "prompt_token_limit": PROMPT_TOKEN_LIMIT if prompt_tokens is not None else None,
        "cases": [
            {
                "run_index": case.run_index,
                "thread_id": case.thread_id,
                "status": case.status,
                "production_ready": case.production_ready,
                "input": case.input,
                "output": case.output,
                "audit": case.audit,
                "error_message": case.error_message,
                "trace_name": case.trace_name,
                "extra": case.extra,
            }
            for case in cases
        ],
        "finished_at": utc_now(),
    }

    return ObservationResult(
        kind="dataset",
        name=options.suite,
        status=trace["status"],
        production_ready=production_ready,
        thread_id=thread_id,
        trace=trace,
        cases=cases,
        audit_markdown_name="01_dataset_cases.md",
    )
