from __future__ import annotations

import json
from html import unescape
from pathlib import Path
from typing import Any

from src.backend.observability.common import (
    PACKETS_DIR,
    local_packet_date,
    local_packet_time,
    repo_relative,
    slugify,
    to_vietnam_time,
    vietnam_now,
)
from src.backend.observability.types import ObservationCaseResult, ObservationResult


def make_packet_dir(kind: str, name: str, label: str) -> Path:
    date_dir = PACKETS_DIR / local_packet_date()
    date_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{local_packet_time()}_{slugify(name, max_length=16)}_{slugify(kind, max_length=16)}"
    suffix = slugify(label, max_length=48)
    packet_dir = date_dir / f"{prefix}_{suffix}"
    counter = 2
    while packet_dir.exists():
        packet_dir = date_dir / f"{prefix}_{suffix}-{counter:02d}"
        counter += 1
    packet_dir.mkdir(parents=True)
    return packet_dir


def write_packet(result: ObservationResult, label: str) -> ObservationResult:
    packet_dir = make_packet_dir(result.kind, result.name, label)
    trace = dict(result.trace)
    trace["packet_dir"] = repo_relative(packet_dir)
    trace["packet_written_at_vietnam"] = vietnam_now()
    packet_result = ObservationResult(
        kind=result.kind,
        name=result.name,
        status=result.status,
        production_ready=result.production_ready,
        thread_id=result.thread_id,
        trace=trace,
        cases=result.cases,
        packet_dir=packet_dir,
        audit_markdown_name=result.audit_markdown_name,
    )
    (packet_dir / "trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (packet_dir / "00_general.md").write_text(
        render_general(packet_result),
        encoding="utf-8",
    )

    if result.kind == "dataset":
        write_dataset_packet_files(packet_dir, result)
    elif result.kind == "node":
        write_node_packet_files(packet_dir, result.trace)
    elif result.kind == "checkpoint-node":
        write_node_packet_files(packet_dir, result.trace)
    elif result.kind == "full":
        write_full_packet_files(packet_dir, trace)
    elif result.kind == "run-readout":
        write_run_readout_packet_files(packet_dir, trace)

    return packet_result


def render_general(result: ObservationResult) -> str:
    run_summary = result.trace.get("db_readback")
    lines = [
        f"# Raven Observation: {result.name}",
        "",
        f"- Kind: `{result.kind}`",
        f"- Status: `{result.status}`",
        f"- Production ready: {format_scalar(result.production_ready)}",
        f"- Thread: `{result.thread_id}`",
    ]
    for label, key in (
        ("Packet written Vietnam", "packet_written_at_vietnam"),
        ("Started Vietnam", "started_at"),
        ("Finished Vietnam", "finished_at"),
    ):
        value = result.trace.get(key)
        if value:
            lines.append(f"- {label}: `{to_vietnam_time(value)}`")
    if result.cases:
        passed = sum(1 for case in result.cases if case.production_ready)
        lines.append(f"- Cases passed: `{passed}` / `{len(result.cases)}`")
    dataset = result.trace.get("dataset")
    if dataset:
        lines.append(f"- Dataset: `{dataset}`")
    output = result.trace.get("output")
    run_id = output.get("run_id") if isinstance(output, dict) else result.trace.get("run_id")
    if run_id:
        lines.append(f"- Raven run_id: `{run_id}`")
    if isinstance(run_summary, dict) and run_summary.get("found"):
        metadata = run_summary.get("metadata", {})
        counts = run_summary.get("counts", {})
        lines.extend(
            [
                f"- Request: {metadata.get('request')}",
                f"- Queries: `{counts.get('query_count', 0)}`",
                f"- Candidates: `{counts.get('candidate_count', 0)}`",
            ]
        )
    lines.extend(["", "## Node Dashboard", ""])
    lines.extend(render_node_dashboard(result.trace, result.cases))
    lines.extend(
        [
            "",
            "## Concise IO",
            "",
        ]
    )
    lines.extend(render_concise_io(result.trace, result.cases))
    lines.extend(
        [
            "",
            "## Packet Contract",
            "",
            "- Human markdown files are for reading and audit.",
            "- `trace.json` is the machine-readable record.",
            "- Fill the Duc audit lines directly while reviewing.",
            "",
        ]
    )
    return "\n".join(lines)


def render_node_dashboard(
    trace: dict[str, Any],
    cases: list[ObservationCaseResult],
) -> list[str]:
    if cases:
        passed = sum(1 for case in cases if case.production_ready)
        return [
            "| Node | Status | Input | Output |",
            "|---|---|---|---|",
            (
                f"| {human_title(str(trace.get('suite') or trace.get('kind') or 'dataset'))} "
                f"| {status_word(passed == len(cases) and bool(cases))} "
                f"| {len(cases)} case(s) "
                f"| {passed}/{len(cases)} passed |"
            ),
        ]

    run_summary = trace.get("db_readback")
    if isinstance(run_summary, dict) and run_summary.get("found"):
        return render_run_node_dashboard(run_summary)

    node = trace.get("node")
    if node:
        return [
            "| Node | Status | Input | Output |",
            "|---|---|---|---|",
            (
                f"| {human_title(str(node))} "
                f"| {status_word(trace.get('status') == 'passed')} "
                f"| {summarize_value(trace.get('input_state', {}))} "
                f"| {summarize_value(trace.get('output', {}))} |"
            ),
        ]

    return [
        "| Node | Status | Input | Output |",
        "|---|---|---|---|",
        (
            f"| {human_title(str(trace.get('kind') or 'run'))} "
            f"| {status_word(trace.get('status') == 'passed')} "
            f"| {summarize_value(trace.get('input_state', {}))} "
            f"| {summarize_value(trace.get('output', {}))} |"
        ),
    ]


def render_run_node_dashboard(run_summary: dict[str, Any]) -> list[str]:
    metadata = run_summary.get("metadata", {})
    counts = run_summary.get("counts", {})
    search = run_summary.get("search", {})
    query_count = counts.get("query_count", 0)
    candidate_count = counts.get("candidate_count", 0)
    ranked_count = sum(1 for row in run_summary.get("tier1_rows", []) if row.get("final_decision"))
    final_count = len(run_summary.get("final_decisions", []))
    tier1_decision_counts = ", ".join(
        f"{row.get('decision')}: {row.get('count')}"
        for row in counts.get("tier1_decision_counts", [])
    )
    final_label_counts = ", ".join(
        f"{row.get('label')}: {row.get('count')}"
        for row in counts.get("final_label_counts", [])
    )
    api_ok = all(
        row.get("search_list_status") == 200 and row.get("video_list_status") == 200
        for row in search.get("api_logs", [])
    )
    rows = [
        "| Node | Status | Input | Output |",
        "|---|---|---|---|",
        (
            f"| create_run | {status_word(bool(metadata.get('id')))} "
            f"| request: {clean_text(metadata.get('request'))} "
            f"| run `{metadata.get('id')}` |"
        ),
        (
            f"| enricher | {status_word(query_count > 0)} "
            f"| request: {clean_text(metadata.get('request'))} "
            f"| {query_count} query/queries |"
        ),
        (
            f"| youtube_search | {status_word(api_ok and candidate_count > 0)} "
            f"| {query_count} query/queries "
            f"| {candidate_count} candidate(s) |"
        ),
        (
            f"| ranker_tier1 | {status_word(ranked_count > 0)} "
            f"| {candidate_count} candidate(s) "
            f"| {tier1_decision_counts or 'no decisions'} |"
        ),
        (
            f"| ranker_tier1_final | {status_word(final_count > 0)} "
            f"| {ranked_count} ranked candidate(s) "
            f"| {final_label_counts or 'no final labels'} |"
        ),
    ]
    return rows


def render_concise_io(
    trace: dict[str, Any],
    cases: list[ObservationCaseResult],
) -> list[str]:
    if cases:
        return [
            f"- Input: `{len(cases)}` dataset case(s).",
            f"- Output: `{sum(1 for case in cases if case.production_ready)}` passed.",
        ]

    run_summary = trace.get("db_readback")
    if isinstance(run_summary, dict) and run_summary.get("found"):
        metadata = run_summary.get("metadata", {})
        counts = run_summary.get("counts", {})
        search = run_summary.get("search", {})
        return [
            f"- Input request: {clean_text(metadata.get('request'))}",
            f"- Search output: `{counts.get('query_count', 0)}` query/queries, `{counts.get('candidate_count', 0)}` candidate(s).",
            f"- YouTube filter: {format_filter_rollup(search.get('filter_stats', []))}",
            f"- Tier 1 output: {format_count_rows(counts.get('tier1_decision_counts', []), 'decision')}",
            f"- Final output: {format_count_rows(counts.get('final_label_counts', []), 'label')}",
        ]

    return [
        f"- Input: {summarize_value(trace.get('input_state', {}))}",
        f"- Output: {summarize_value(trace.get('output', {}))}",
    ]


def write_dataset_packet_files(packet_dir: Path, result: ObservationResult) -> None:
    node = result.name
    slug = slugify(node, max_length=36)
    (packet_dir / f"01_{slug}_inputs.md").write_text(
        render_dataset_inputs(node, result.cases),
        encoding="utf-8",
    )
    (packet_dir / f"02_{slug}_outputs.md").write_text(
        render_dataset_outputs(node, result.cases),
        encoding="utf-8",
    )


def render_dataset_inputs(node: str, cases: list[ObservationCaseResult]) -> str:
    lines = [f"# {human_title(node)} Inputs", ""]
    if not cases:
        lines.append("No cases.")
        return "\n".join(lines)
    for case in cases:
        lines.extend(render_case_header(case))
        lines.extend(["### Input", ""])
        lines.extend(render_human_value(case.input))
        lines.append("")
    return "\n".join(lines)


def render_dataset_outputs(node: str, cases: list[ObservationCaseResult]) -> str:
    lines = [f"# {human_title(node)} Outputs", ""]
    if not cases:
        lines.append("No cases.")
        return "\n".join(lines)
    for case in cases:
        lines.extend(render_case_header(case))
        lines.extend(["### LLM output", ""])
        lines.extend(render_human_value(case.output or {}))
        lines.extend(["", "### Duc audit line", "", ""])
        if case.audit:
            lines.extend(["### Harness audit", ""])
            lines.extend(render_human_value(case.audit))
            lines.append("")
    return "\n".join(lines)


def render_case_header(case: ObservationCaseResult) -> list[str]:
    lines = [
        f"## Case {case.run_index}",
        "",
        f"- Status: `{case.status}`",
        f"- Production ready: {format_scalar(case.production_ready)}",
    ]
    if case.error_message:
        lines.append(f"- Error: {case.error_message}")
    if case.trace_name:
        lines.append(f"- Trace name: `{case.trace_name}`")
    lines.append("")
    return lines


def write_node_packet_files(packet_dir: Path, trace: dict[str, Any]) -> None:
    node = str(trace.get("node") or "node")
    slug = slugify(node, max_length=36)
    (packet_dir / f"01_{slug}_input.md").write_text(
        render_node_input(trace),
        encoding="utf-8",
    )
    (packet_dir / f"02_{slug}_output.md").write_text(
        render_node_output(trace),
        encoding="utf-8",
    )


def render_node_input(trace: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {human_title(str(trace.get('node') or 'Node'))} Input",
            "",
            f"- Graph: `{trace.get('graph')}`",
            f"- Node: `{trace.get('node')}`",
            f"- Status: `{trace.get('status')}`",
            "",
            "## Input State",
            "",
            *render_human_value(trace.get("input_state", {})),
            "",
        ]
    )


def render_node_output(trace: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {human_title(str(trace.get('node') or 'Node'))} Output",
            "",
            f"- Graph: `{trace.get('graph')}`",
            f"- Node: `{trace.get('node')}`",
            f"- Status: `{trace.get('status')}`",
            "",
            "## LLM output",
            "",
            *render_human_value(trace.get("output", {})),
            "",
            "## Duc audit line",
            "",
            "",
        ]
    )


def write_full_packet_files(packet_dir: Path, trace: dict[str, Any]) -> None:
    output = trace.get("output", {})
    run_summary = trace.get("db_readback", {})
    (packet_dir / "01_enricher_input.md").write_text(
        render_named_input("Enricher", trace.get("input_state", {})),
        encoding="utf-8",
    )
    enricher_output = {}
    if isinstance(output, dict):
        enricher_output = {
            "queries": output.get("queries", []),
            "key_words": output.get("key_words", []),
        }
    (packet_dir / "02_enricher_output.md").write_text(
        render_named_output("Enricher", enricher_output),
        encoding="utf-8",
    )
    (packet_dir / "03_youtube_search_in_out.md").write_text(
        render_search_in_out(enricher_output, run_summary),
        encoding="utf-8",
    )
    tier1_rows = run_summary.get("tier1_rows", [])
    final_input_rows = [row for row in tier1_rows if is_final_selector_input(row)]
    (packet_dir / "04_ranker_tier1.md").write_text(
        render_tier1_file(tier1_rows),
        encoding="utf-8",
    )
    (packet_dir / "05_ranker_tier1_final.md").write_text(
        render_final_file(final_input_rows, run_summary.get("final_decisions", [])),
        encoding="utf-8",
    )


def write_run_readout_packet_files(packet_dir: Path, trace: dict[str, Any]) -> None:
    run_summary = trace.get("db_readback", {})
    (packet_dir / "01_youtube_search_in_out.md").write_text(
        render_search_in_out({}, run_summary),
        encoding="utf-8",
    )
    tier1_rows = run_summary.get("tier1_rows", [])
    final_input_rows = [row for row in tier1_rows if is_final_selector_input(row)]
    (packet_dir / "02_ranker_tier1.md").write_text(
        render_tier1_file(tier1_rows),
        encoding="utf-8",
    )
    (packet_dir / "03_ranker_tier1_final.md").write_text(
        render_final_file(final_input_rows, run_summary.get("final_decisions", [])),
        encoding="utf-8",
    )


def render_named_input(name: str, value: Any) -> str:
    return "\n".join(
        [
            f"# {name} Input",
            "",
            "## Report",
            "",
            f"- Fields: `{len(value) if isinstance(value, dict) else 1}`",
            "",
            "## Details",
            "",
            *render_human_value(value),
            "",
        ]
    )


def render_named_output(name: str, value: Any) -> str:
    report_lines = [f"- Fields: `{len(value) if isinstance(value, dict) else 1}`"]
    if isinstance(value, dict) and "queries" in value:
        report_lines = [
            f"- Queries: `{len(value.get('queries') or [])}`",
            f"- Key words: `{len(value.get('key_words') or [])}`",
        ]
    return "\n".join(
        [
            f"# {name} Output",
            "",
            "## Report",
            "",
            *report_lines,
            "",
            "## Details",
            "",
            *render_human_value(value),
            "",
            "## Duc audit line",
            "",
            "",
        ]
    )


def render_search_in_out(search_input: dict[str, Any], run_summary: dict[str, Any]) -> str:
    if not run_summary.get("found"):
        return "# YouTube Search In/Out\n\nNo DB run metadata found.\n"
    search = run_summary.get("search", {})
    metadata = run_summary.get("metadata", {})
    lines = [
        "# YouTube Search In/Out",
        "",
        "## Report",
        "",
        *render_search_report(run_summary),
        "",
        "## Input",
        "",
        f"- Run: `{metadata.get('id')}`",
        f"- Request: {metadata.get('request')}",
    ]
    queries = search_input.get("queries") or [row.get("query") for row in search.get("queries", [])]
    key_words = search_input.get("key_words") or []
    if queries:
        lines.append("- Queries:")
        for query in queries:
            lines.append(f"  - {clean_text(query)}")
    if key_words:
        lines.append("- Key words:")
        for key_word in key_words:
            lines.append(f"  - {clean_text(key_word)}")

    lines.extend(["", "## Details", ""])
    count_by_query = {
        row.get("query"): row.get("candidate_count", 0)
        for row in search.get("candidate_counts", [])
    }
    api_by_query = {row.get("query"): row for row in search.get("api_logs", [])}
    filter_by_query = {row.get("query"): row for row in search.get("filter_stats", [])}
    candidates_by_query: dict[str, list[dict[str, Any]]] = {}
    for row in run_summary.get("tier1_rows", []):
        candidates_by_query.setdefault(str(row.get("query", "")), []).append(row)

    for row in search.get("queries", []):
        query = row.get("query")
        api = api_by_query.get(query, {})
        filter_stats = filter_by_query.get(query, {})
        lines.extend(
            [
                f"### Query {row.get('query_index')}: {clean_text(query)}",
                "",
                f"- Source: {row.get('source')}",
                f"- Query row status: `{row.get('status_code')}`",
                f"- YouTube search.list status: `{api.get('search_list_status')}`",
                f"- YouTube videos.list status: `{api.get('video_list_status')}`",
                f"- Raw search items: `{filter_stats.get('raw_items', 0)}`",
                f"- Unique videos: `{filter_stats.get('unique_video_ids', 0)}`",
                f"- Duplicate search hits: `{filter_stats.get('duplicate_items', 0)}`",
                f"- Candidates after filters: `{count_by_query.get(query, 0)}`",
                f"- Filtered out before Tier 1: `{filter_stats.get('filtered_out', 0)}`",
                "",
            ]
        )
        candidates = candidates_by_query.get(str(query), [])
        if not candidates:
            lines.append("No candidate rows found for this query.")
            lines.append("")
            continue
        for candidate in candidates:
            lines.append(f"- {clean_text(candidate.get('title', ''))}")
        lines.append("")
    return "\n".join(lines)


def render_tier1_file(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Ranker Tier 1",
        "",
        "## Report",
        "",
        f"- Candidate count: `{len(rows)}`",
        f"- Tier 1 decision counts: {format_tier1_decision_counts(rows)}",
    ]
    if not rows:
        lines.extend(["", "## Details", "", "No candidate rows."])
        return "\n".join(lines)
    lines.extend(["", "## Audit Index", ""])
    lines.extend(render_tier1_index(rows))
    lines.extend(["", "## Details", ""])
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"### {index}. {clean_text(row.get('title', ''))}",
                "",
                f"- Query: {clean_text(row.get('query'))}",
                f"- Tier 1 decision: `{row.get('final_decision') or 'undecided'}`",
                f"- Channel: {clean_text(row.get('channel_title') or row.get('author_or_channel'))}",
                f"- Date: {row.get('published_at') or ''}",
                f"- Views: `{row.get('view_count') or 0}`",
                f"- Link: {clean_text(row.get('link'))}",
                "",
                "Preview:",
                "",
                f"> {clean_text(row.get('description_excerpt'), max_length=360)}",
                "",
                "Ranker reasoning:",
                "",
                f"> {clean_text(row.get('final_verdict'), max_length=360)}",
                "",
                "Duc audit line:",
                "",
                "",
            ]
        )
    return "\n".join(lines)


def render_final_file(
    input_rows: list[dict[str, Any]],
    output_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# Ranker Tier 1 Final",
        "",
        "## Report",
        "",
        f"- Final selector input count: `{len(input_rows)}`",
        f"- Final label counts: {format_final_label_counts(output_rows)}",
    ]
    if not output_rows:
        lines.extend(["", "## Details", "", "No final decision rows."])
        return "\n".join(lines)
    lines.extend(["", "## Audit Index", ""])
    for index, row in enumerate(output_rows, start=1):
        lines.append(
            f"- {index}. `{row.get('sexy_label')}` | {clean_text(row.get('title', ''), max_length=110)}"
        )
    lines.extend(["", "## Details", ""])
    for index, row in enumerate(output_rows, start=1):
        lines.extend(
            [
                f"### {index}. {clean_text(row.get('title', ''))}",
                "",
                f"- Query: {clean_text(row.get('query'))}",
                f"- Tier 1 decision: `{row.get('final_decision') or 'undecided'}`",
                f"- Date: {row.get('published_at') or ''}",
                f"- Views: `{row.get('view_count') or 0}`",
                f"- Final label: `{row.get('sexy_label')}`",
                "",
                "Final selector reason:",
                "",
                f"> {clean_text(row.get('final_reason'), max_length=360)}",
                "",
                "Duc audit line:",
                "",
                "",
            ]
        )
    return "\n".join(lines)


def is_final_selector_input(row: dict[str, Any]) -> bool:
    return row.get("final_decision") == "keep"


def human_title(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def status_word(success: bool) -> str:
    return "success" if success else "needs review"


def summarize_value(value: Any) -> str:
    if isinstance(value, dict):
        if "request" in value:
            return f"request: {clean_text(value.get('request'))}"
        if "query" in value:
            return f"query: {clean_text(value.get('query'))}"
        if "queries" in value:
            queries = value.get("queries") or []
            return f"{len(queries)} query/queries"
        if "ranker_tier1_results" in value:
            results = value.get("ranker_tier1_results") or []
            done = sum(1 for item in results if isinstance(item, dict) and item.get("done"))
            return f"{done}/{len(results)} ranked"
        if "ranker_tier1_final_done" in value:
            return f"final done: {format_scalar(value.get('ranker_tier1_final_done'))}"
        if "yt_search_done" in value:
            return f"youtube done: {format_scalar(value.get('yt_search_done'))}"
        return f"{len(value)} field(s)"
    if isinstance(value, list):
        return f"{len(value)} item(s)"
    return clean_text(value)


def format_count_rows(rows: list[dict[str, Any]], key: str) -> str:
    if not rows:
        return "none"
    return ", ".join(f"`{row.get(key)}` {row.get('count')}" for row in rows)


def format_filter_rollup(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "not available"
    raw_items = sum(int(row.get("raw_items") or 0) for row in rows)
    unique_video_ids = sum(int(row.get("unique_video_ids") or 0) for row in rows)
    candidates = sum(int(row.get("candidate_count") or 0) for row in rows)
    filtered_out = sum(int(row.get("filtered_out") or 0) for row in rows)
    return (
        f"`{raw_items}` raw hits, `{unique_video_ids}` unique videos, "
        f"`{candidates}` candidates, `{filtered_out}` filtered out"
    )


def render_search_report(run_summary: dict[str, Any]) -> list[str]:
    search = run_summary.get("search", {})
    counts = run_summary.get("counts", {})
    filter_stats = search.get("filter_stats", [])
    lines = [
        f"- Queries: `{counts.get('query_count', 0)}`",
        f"- Candidate rows after YouTube filters: `{counts.get('candidate_count', 0)}`",
        f"- Filter rollup: {format_filter_rollup(filter_stats)}",
    ]
    if filter_stats:
        lines.extend(["", "| Query | Raw hits | Unique videos | Candidates | Filtered out |", "|---|---:|---:|---:|---:|"])
        for row in filter_stats:
            lines.append(
                "| "
                f"{clean_text(row.get('query'), max_length=80)} "
                f"| {int(row.get('raw_items') or 0)} "
                f"| {int(row.get('unique_video_ids') or 0)} "
                f"| {int(row.get('candidate_count') or 0)} "
                f"| {int(row.get('filtered_out') or 0)} |"
            )
    return lines


def format_tier1_decision_counts(rows: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        decision = str(row.get("final_decision") or "undecided")
        counts[decision] = counts.get(decision, 0) + 1
    return ", ".join(f"`{decision}` {count}" for decision, count in sorted(counts.items()))


def format_final_label_counts(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "none"
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get("sexy_label") or "unlabeled")
        counts[label] = counts.get(label, 0) + 1
    return ", ".join(f"`{label}` {count}" for label, count in sorted(counts.items()))


def render_tier1_index(rows: list[dict[str, Any]]) -> list[str]:
    lines = ["| # | Decision | Title | Views |", "|---:|---|---|---:|"]
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"| {index} | `{row.get('final_decision') or 'undecided'}` | "
            f"{clean_text(row.get('title', ''), max_length=100)} | "
            f"{int(row.get('view_count') or 0)} |"
        )
    return lines


def clean_text(value: Any, *, max_length: int = 500) -> str:
    if value is None:
        return ""
    text = " ".join(unescape(str(value)).split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def render_human_value(value: Any, *, indent: int = 0) -> list[str]:
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            return [f"{pad}- None"]
        lines: list[str] = []
        for key, item in value.items():
            label = human_title(str(key))
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}- {label}:")
                lines.extend(render_human_value(item, indent=indent + 2))
            else:
                lines.append(f"{pad}- {label}: {format_scalar(item)}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{pad}- None"]
        lines = []
        for index, item in enumerate(value, start=1):
            if isinstance(item, dict):
                lines.append(f"{pad}- Item {index}:")
                lines.extend(render_human_value(item, indent=indent + 2))
            elif isinstance(item, list):
                lines.append(f"{pad}- Item {index}:")
                lines.extend(render_human_value(item, indent=indent + 2))
            else:
                lines.append(f"{pad}- {format_scalar(item)}")
        return lines
    return [f"{pad}- {format_scalar(value)}"]


def format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"`{value}`"
    return clean_text(value)
