from __future__ import annotations

import sys
from pathlib import Path

# ruff: noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.run_observation import main as observation_main


if __name__ == "__main__":
    print(
        "Deprecated: use `eval/run_observation.py dataset --suite ranker_tier1_final ...`.",
        file=sys.stderr,
    )
    passthrough = sys.argv[1:]
    has_file_arg = any(arg == "--file" or arg.startswith("--file=") for arg in passthrough)
    if not has_file_arg and "-h" not in passthrough and "--help" not in passthrough:
        passthrough = ["--file", "eval/ranker_tier1_final_cases.jsonl", *passthrough]
    sys.argv = [
        sys.argv[0],
        "dataset",
        "--suite",
        "ranker_tier1_final",
        *passthrough,
    ]
    raise SystemExit(observation_main())
