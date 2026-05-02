import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.backend.observability import packets
from src.backend.observability.types import ObservationCaseResult, ObservationResult


class PacketOutputsTest(unittest.TestCase):
    def test_dataset_packet_uses_human_input_output_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            original_packets_dir = packets.PACKETS_DIR
            packets.PACKETS_DIR = Path(temp_dir)
            try:
                result = ObservationResult(
                    kind="dataset",
                    name="enricher",
                    status="passed",
                    production_ready=True,
                    thread_id="thread-1",
                    trace={"kind": "dataset", "dataset": "eval/enricher_cases.jsonl"},
                    cases=[
                        ObservationCaseResult(
                            run_index=1,
                            thread_id="case-thread-1",
                            status="passed",
                            production_ready=True,
                            input={"request": "how to grow a youtube channel"},
                            output={
                                "queries": ["how to grow a youtube channel"],
                                "key_words": ["youtube", "channel"],
                            },
                            audit={"query_count_ok": True},
                        )
                    ],
                )

                packet = packets.write_packet(result, label="packet-shape")

                packet_dir = packet.packet_dir
                self.assertIsNotNone(packet_dir)
                assert packet_dir is not None
                self.assertRegex(packet_dir.parent.name, r"^\d{2}-[A-Za-z]{3}-\d{4}$")
                self.assertRegex(packet_dir.name, r"^\d{2}:\d{2}:\d{2}_enricher_dataset_")
                self.assertTrue((packet_dir / "trace.json").is_file())
                self.assertTrue((packet_dir / "00_general.md").is_file())
                self.assertTrue((packet_dir / "01_enricher_inputs.md").is_file())
                outputs = (packet_dir / "02_enricher_outputs.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("### Duc audit line", outputs)
                self.assertNotIn("```json", outputs)
            finally:
                packets.PACKETS_DIR = original_packets_dir

    def test_run_readout_packet_writes_youtube_and_llm_audit_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            original_packets_dir = packets.PACKETS_DIR
            packets.PACKETS_DIR = Path(temp_dir)
            try:
                result = ObservationResult(
                    kind="run-readout",
                    name="raven",
                    status="passed",
                    production_ready=True,
                    thread_id="thread-2",
                    trace={
                        "kind": "run-readout",
                        "run_id": 6,
                        "db_readback": {
                            "found": True,
                            "metadata": {
                                "id": 6,
                                "request": "how to grow a youtube channel",
                            },
                            "counts": {
                                "query_count": 1,
                                "candidate_count": 1,
                                "tier1_decision_counts": [{"decision": "keep", "count": 1}],
                                "final_label_counts": [{"label": "click", "count": 1}],
                            },
                            "search": {
                                "queries": [
                                    {
                                        "id": 1,
                                        "query_index": 0,
                                        "source": "youtube",
                                        "status_code": 200,
                                        "query": "how to grow a youtube channel",
                                    }
                                ],
                                "api_logs": [
                                    {
                                        "query": "how to grow a youtube channel",
                                        "search_list_status": 200,
                                        "video_list_status": 200,
                                    }
                                ],
                                "candidate_counts": [
                                    {
                                        "query": "how to grow a youtube channel",
                                        "candidate_count": 1,
                                    }
                                ],
                            },
                            "tier1_rows": [
                                {
                                    "id": 101,
                                    "query": "how to grow a youtube channel",
                                    "title": "Candidate title",
                                    "description_excerpt": "Candidate description excerpt",
                                    "link": "https://youtube.com/watch?v=abc",
                                    "author_or_channel": "Channel",
                                    "published_at": "2026-04-30T00:00:00Z",
                                    "view_count": 123,
                                    "final_decision": "keep",
                                    "final_verdict": "specific mechanism",
                                }
                            ],
                            "final_decisions": [
                                {
                                    "id": 101,
                                    "query": "how to grow a youtube channel",
                                    "title": "Candidate title",
                                    "published_at": "2026-04-30T00:00:00Z",
                                    "view_count": 123,
                                    "final_decision": "keep",
                                    "sexy_label": "click",
                                    "final_reason": "best concrete mechanism",
                                }
                            ],
                        },
                    },
                    cases=[],
                )

                packet = packets.write_packet(result, label="run-0006")

                packet_dir = packet.packet_dir
                self.assertIsNotNone(packet_dir)
                assert packet_dir is not None
                self.assertTrue((packet_dir / "trace.json").is_file())
                general = (packet_dir / "00_general.md").read_text(encoding="utf-8")
                youtube = (packet_dir / "01_youtube_search_in_out.md").read_text(
                    encoding="utf-8"
                )
                tier1 = (packet_dir / "02_ranker_tier1.md").read_text(encoding="utf-8")
                final = (packet_dir / "03_ranker_tier1_final.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("## Node Dashboard", general)
                self.assertIn("ranker_tier1_final", general)
                self.assertIn("# YouTube Search In/Out", youtube)
                self.assertIn("### Query 0", youtube)
                self.assertIn("- Candidate title", youtube)
                self.assertIn("- Candidate count: `1`", tier1)
                self.assertIn("### 1. Candidate title", tier1)
                self.assertIn("Duc audit line:", tier1)
                self.assertIn("- Date: 2026-04-30T00:00:00Z", final)
                self.assertIn("- Views: `123`", final)
                self.assertIn("- Final label: `click`", final)
                self.assertIn("Duc audit line:", final)
                self.assertNotIn("```json", youtube)
            finally:
                packets.PACKETS_DIR = original_packets_dir


if __name__ == "__main__":
    unittest.main()
