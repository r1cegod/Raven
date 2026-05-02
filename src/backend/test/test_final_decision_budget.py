import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.backend.db import (
    candidates_rank,
    create_candidate,
    create_query,
    create_run,
    init,
)
from src.backend.observability.db_readback import summarize_run


class RunReadoutTest(unittest.TestCase):
    def test_summarize_run_reports_counts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "raven.sqlite"
            db = init(str(db_path))
            try:
                run_id = create_run(db, "how to grow a youtube channel")
                query_id = create_query(
                    db,
                    run_id,
                    raw_response="{}",
                    status_code=200,
                    query="how to grow a youtube channel",
                    query_index=0,
                    source="youtube",
                )
                candidate_id = create_candidate(
                    db,
                    run_id,
                    query_id,
                    source="youtube",
                    platform_id="video-1",
                    title="Candidate 1",
                    description="description",
                    link="https://youtube.com/watch?v=1",
                    author_or_channel="channel",
                    published_at="2026-04-30T00:00:00Z",
                    channel_id="channel-id",
                    channel_title="channel",
                    view_count=1,
                )
                self.assertIsNotNone(candidate_id)
                candidates_rank(db, candidate_id, "keep", "reason")
            finally:
                db.close()

            summary = summarize_run(run_id, db_path)

        self.assertTrue(summary["found"])
        self.assertEqual(summary["counts"]["query_count"], 1)
        self.assertEqual(summary["counts"]["candidate_count"], 1)
        self.assertEqual(
            summary["counts"]["tier1_decision_counts"],
            [{"decision": "keep", "count": 1}],
        )


if __name__ == "__main__":
    unittest.main()
