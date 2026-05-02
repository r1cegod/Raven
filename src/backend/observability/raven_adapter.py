from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from src.backend.observability.common import (
    DEFAULT_DB_PATH,
    EVAL_DIR,
    serialize_value,
    utc_now,
)
from src.backend.observability.db_readback import summarize_run
from src.backend.observability.types import ObservationResult


class RavenAdapter:
    graph_name = "raven"

    @staticmethod
    def _runtime() -> Any:
        import src.backend.youtube_ranker_tier1 as runtime

        return runtime

    @staticmethod
    def _graph_runtime() -> Any:
        import src.backend.raven_graph as runtime

        return runtime

    def node_map(self) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
        runtime = self._runtime()
        graph_runtime = self._graph_runtime()
        return {
            "create_run": graph_runtime.run_create,
            "enricher": runtime.enricher,
            "youtube_search": runtime.youtube_search,
            "ranker_tier1": runtime.ranker_tier_1,
            "ranker_tier1_final": runtime.ranker_tier1_final,
        }

    def run_full(self, request: str, *, db_path: Path = DEFAULT_DB_PATH) -> ObservationResult:
        thread_id = str(uuid4())
        input_state = {"request": request}
        trace: dict[str, Any] = {
            "kind": "full",
            "graph": self.graph_name,
            "thread_id": thread_id,
            "input_state": input_state,
            "started_at": utc_now(),
            "status": "started",
        }
        try:
            runtime = self._graph_runtime()
            output = serialize_value(
                runtime.raven_graph.invoke(
                    input_state,
                    config={"configurable": {"thread_id": thread_id}},
                )
            )
            trace.update(
                {
                    "status": "passed",
                    "output": output,
                    "finished_at": utc_now(),
                }
            )
            run_id = output.get("run_id") if isinstance(output, dict) else None
            if isinstance(run_id, int):
                trace["db_readback"] = summarize_run(run_id, db_path)
        except Exception as exc:  # noqa: BLE001
            trace.update(
                {
                    "status": "error",
                    "output": {"error_type": exc.__class__.__name__, "error_message": str(exc)},
                    "traceback": traceback.format_exc(),
                    "finished_at": utc_now(),
                }
            )

        return ObservationResult(
            kind="full",
            name=self.graph_name,
            status=trace["status"],
            production_ready=trace["status"] == "passed",
            thread_id=thread_id,
            trace=trace,
            cases=[],
        )

    def read_run(self, run_id: int, *, db_path: Path = DEFAULT_DB_PATH) -> ObservationResult:
        thread_id = str(uuid4())
        run_summary = summarize_run(run_id, db_path)
        status = "passed" if run_summary.get("found") else "error"
        trace = {
            "kind": "run-readout",
            "graph": self.graph_name,
            "thread_id": thread_id,
            "run_id": run_id,
            "db_path": str(db_path),
            "started_at": utc_now(),
            "status": status,
            "db_readback": run_summary,
            "finished_at": utc_now(),
        }
        return ObservationResult(
            kind="run-readout",
            name=self.graph_name,
            status=status,
            production_ready=status == "passed",
            thread_id=thread_id,
            trace=trace,
            cases=[],
        )

    def run_node(self, node: str, state: dict[str, Any]) -> ObservationResult:
        thread_id = str(uuid4())
        trace: dict[str, Any] = {
            "kind": "node",
            "graph": self.graph_name,
            "node": node,
            "thread_id": thread_id,
            "input_state": state,
            "started_at": utc_now(),
            "status": "started",
        }
        try:
            nodes = self.node_map()
            if node not in nodes:
                raise ValueError(f"Unknown Raven node: {node}")
            output = serialize_value(nodes[node](state))
            trace.update(
                {
                    "status": "passed",
                    "output": output,
                    "finished_at": utc_now(),
                }
            )
        except Exception as exc:  # noqa: BLE001
            trace.update(
                {
                    "status": "error",
                    "output": {"error_type": exc.__class__.__name__, "error_message": str(exc)},
                    "traceback": traceback.format_exc(),
                    "finished_at": utc_now(),
                }
            )

        return ObservationResult(
            kind="node",
            name=f"{self.graph_name}_{node}",
            status=trace["status"],
            production_ready=trace["status"] == "passed",
            thread_id=thread_id,
            trace=trace,
            cases=[],
        )

    def run_checkpoint_node(
        self,
        *,
        thread_id: str,
        checkpoint_id: str,
        node: str,
        checkpoint_db: Path | None = None,
    ) -> ObservationResult:
        checkpoint_db = checkpoint_db or EVAL_DIR / "checkpoints" / "raven.sqlite"
        trace: dict[str, Any] = {
            "kind": "checkpoint-node",
            "graph": self.graph_name,
            "node": node,
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "checkpoint_db": str(checkpoint_db),
            "started_at": utc_now(),
            "status": "started",
        }
        try:
            nodes = self.node_map()
            if node not in nodes:
                raise ValueError(f"Unknown Raven node: {node}")
            from langgraph.checkpoint.sqlite import SqliteSaver

            checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
            runtime = self._graph_runtime()
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                }
            }
            with SqliteSaver.from_conn_string(str(checkpoint_db)) as checkpointer:
                graph = runtime.graph.compile(checkpointer=checkpointer)
                snapshot = graph.get_state(config)
            state = serialize_value(snapshot.values)
            output = serialize_value(nodes[node](dict(snapshot.values)))
            trace.update(
                {
                    "status": "passed",
                    "input_state": state,
                    "output": output,
                    "finished_at": utc_now(),
                }
            )
        except Exception as exc:  # noqa: BLE001
            trace.update(
                {
                    "status": "error",
                    "input_state": trace.get("input_state", {}),
                    "output": {"error_type": exc.__class__.__name__, "error_message": str(exc)},
                    "traceback": traceback.format_exc(),
                    "finished_at": utc_now(),
                }
            )

        return ObservationResult(
            kind="checkpoint-node",
            name=f"{self.graph_name}_{node}",
            status=trace["status"],
            production_ready=trace["status"] == "passed",
            thread_id=thread_id,
            trace=trace,
            cases=[],
        )


def get_graph_adapter(graph_name: str) -> RavenAdapter:
    if graph_name != "raven":
        raise ValueError(f"Unknown graph adapter: {graph_name}")
    return RavenAdapter()


def parse_state_json(raw_state: str) -> dict[str, Any]:
    parsed = json.loads(raw_state)
    if not isinstance(parsed, dict):
        raise ValueError("--state-json must decode to a JSON object.")
    return parsed
