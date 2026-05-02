from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import uuid4

# ruff: noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

from src.backend.observability.common import DEFAULT_DB_PATH, repo_relative, utc_now
from src.backend.observability.eval_suites import DatasetOptions, run_dataset
from src.backend.observability.packets import write_packet
from src.backend.observability.raven_adapter import get_graph_adapter, parse_state_json
from src.backend.observability.types import ObservationCaseResult, ObservationResult


load_dotenv(REPO_ROOT / ".env")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Raven observation harness.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dataset = subparsers.add_parser("dataset", help="Run a JSONL eval suite.")
    dataset.add_argument(
        "--suite",
        required=True,
        choices=("enricher", "ranker_tier1", "ranker_tier1_final"),
    )
    dataset.add_argument("--file", required=True)
    dataset.add_argument("--mode", choices=("single", "multi"), default="multi")
    dataset.add_argument("--workers", type=int, default=None)
    dataset.add_argument("--model", default=None)
    dataset.add_argument("--temperature", type=float, default=0.7)

    full = subparsers.add_parser("full", help="Run a full graph.")
    full.add_argument("--graph", required=True, choices=("raven",))
    full.add_argument("--request", required=True)
    full.add_argument("--db-path", default=str(DEFAULT_DB_PATH))

    read_run = subparsers.add_parser("read-run", help="Summarize an existing DB run.")
    read_run.add_argument("--graph", required=True, choices=("raven",))
    read_run.add_argument("--run-id", required=True, type=int)
    read_run.add_argument("--db-path", default=str(DEFAULT_DB_PATH))

    node = subparsers.add_parser("node", help="Run a focused node.")
    node.add_argument("--graph", required=True, choices=("raven",))
    node.add_argument("--node", required=True)
    node.add_argument("--state-json", required=True)

    checkpoint = subparsers.add_parser(
        "checkpoint-node",
        help="Replay a node from a persisted LangGraph checkpoint.",
    )
    checkpoint.add_argument("--graph", required=True, choices=("raven",))
    checkpoint.add_argument("--thread-id", required=True)
    checkpoint.add_argument("--checkpoint-id", required=True)
    checkpoint.add_argument("--node", required=True)
    checkpoint.add_argument(
        "--checkpoint-db",
        default=str(REPO_ROOT / "eval/checkpoints/raven.sqlite"),
    )
    return parser


def print_dataset_summary(result: ObservationResult) -> None:
    print(f"Thread: {result.thread_id}")
    print(f"Suite: {result.name}")
    print(f"Dataset: {result.trace.get('dataset')}")
    prompt_tokens = result.trace.get("prompt_tokens")
    if prompt_tokens is not None:
        print(f"Prompt tokens: {prompt_tokens}/{result.trace.get('prompt_token_limit')}")
    passed = sum(1 for case in result.cases if case.production_ready)
    print(f"Passed: {passed}/{len(result.cases)}")
    output = result.trace.get("output")
    if isinstance(output, dict) and output.get("error_message"):
        print(f"Error: {output['error_message']}")
    if result.packet_dir:
        print(f"Packet: {repo_relative(result.packet_dir)}")

    for case in result.cases:
        print_case_line(case)

    if result.name == "enricher":
        print(f"Production-ready cases: {passed}")
        print(f"Failed cases: {len(result.cases) - passed}")
        print(f"Production ready: {'YES' if result.production_ready else 'NO'}")


def print_case_line(case: ObservationCaseResult) -> None:
    if case.production_ready:
        print(f"[{case.run_index:04d}] ready  thread={case.thread_id}")
        return
    reason = f" reason={case.error_message}" if case.error_message else ""
    print(f"[{case.run_index:04d}] fail   thread={case.thread_id}{reason}")


def print_run_summary(result: ObservationResult) -> None:
    print(f"Thread: {result.thread_id}")
    print(f"Kind: {result.kind}")
    print(f"Name: {result.name}")
    print(f"Status: {result.status}")
    if result.packet_dir:
        print(f"Packet: {repo_relative(result.packet_dir)}")
    output = result.trace.get("output")
    if isinstance(output, dict) and output.get("error_message"):
        print(f"Error: {output['error_message']}")
    run_summary = result.trace.get("db_readback")
    if isinstance(run_summary, dict) and run_summary.get("found"):
        metadata = run_summary.get("metadata", {})
        counts = run_summary.get("counts", {})
        print(f"Run: {metadata.get('id')}")
        print(f"Request: {metadata.get('request')}")
        print(f"Queries: {counts.get('query_count', 0)}")
        print(f"Candidates: {counts.get('candidate_count', 0)}")
        print(f"Tier 1 decisions: {counts.get('tier1_decision_counts', [])}")
        print(f"Final labels: {counts.get('final_label_counts', [])}")


def run_dataset_command(args: argparse.Namespace) -> int:
    try:
        result = run_dataset(
            DatasetOptions(
                suite=args.suite,
                file=args.file,
                mode=args.mode,
                workers=args.workers,
                model=args.model,
                temperature=args.temperature,
            )
        )
    except Exception as exc:  # noqa: BLE001
        thread_id = str(uuid4())
        result = ObservationResult(
            kind="dataset",
            name=args.suite,
            status="error",
            production_ready=False,
            thread_id=thread_id,
            trace={
                "kind": "dataset",
                "suite": args.suite,
                "dataset": args.file,
                "thread_id": thread_id,
                "status": "error",
                "output": {
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
                "finished_at": utc_now(),
            },
            cases=[],
        )
    packet = write_packet(result, label=Path(args.file).stem)
    print_dataset_summary(packet)
    return 0 if packet.production_ready else 1


def run_full_command(args: argparse.Namespace) -> int:
    adapter = get_graph_adapter(args.graph)
    result = adapter.run_full(args.request, db_path=Path(args.db_path))
    packet = write_packet(result, label=args.request)
    print_run_summary(packet)
    return 0 if packet.production_ready else 1


def run_read_run_command(args: argparse.Namespace) -> int:
    adapter = get_graph_adapter(args.graph)
    result = adapter.read_run(args.run_id, db_path=Path(args.db_path))
    packet = write_packet(result, label=f"run-{args.run_id:04d}")
    print_run_summary(packet)
    return 0 if packet.production_ready else 1


def run_node_command(args: argparse.Namespace) -> int:
    adapter = get_graph_adapter(args.graph)
    result = adapter.run_node(args.node, parse_state_json(args.state_json))
    packet = write_packet(result, label=args.node)
    print_run_summary(packet)
    return 0 if packet.production_ready else 1


def run_checkpoint_node_command(args: argparse.Namespace) -> int:
    adapter = get_graph_adapter(args.graph)
    result = adapter.run_checkpoint_node(
        thread_id=args.thread_id,
        checkpoint_id=args.checkpoint_id,
        node=args.node,
        checkpoint_db=Path(args.checkpoint_db),
    )
    packet = write_packet(result, label=args.node)
    print_run_summary(packet)
    return 0 if packet.production_ready else 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "dataset":
        return run_dataset_command(args)
    if args.command == "full":
        return run_full_command(args)
    if args.command == "read-run":
        return run_read_run_command(args)
    if args.command == "node":
        return run_node_command(args)
    if args.command == "checkpoint-node":
        return run_checkpoint_node_command(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
