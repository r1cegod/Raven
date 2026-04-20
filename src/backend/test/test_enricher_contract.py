import unittest

from src.backend.Raven_graph import EnricherOutput, raven_graph
from src.backend.data.prompt.enricher import ENRICHER_PROMPT


class EnricherContractTest(unittest.TestCase):
    def test_prompt_has_production_constraints(self) -> None:
        required_fragments = [
            "Preserve the user's exact target as the first query",
            "Decide how many queries are needed",
            "Do not create fake proper nouns",
            "failure mode",
            "tools, numbers, metrics",
        ]

        for fragment in required_fragments:
            self.assertIn(fragment, ENRICHER_PROMPT)

    def test_graph_exists(self) -> None:
        self.assertIsNotNone(raven_graph)

    def test_structured_output_allows_llm_to_choose_query_count(self) -> None:
        output = EnricherOutput(queries=["how to find leads"])
        self.assertEqual(output.queries, ["how to find leads"])


if __name__ == "__main__":
    unittest.main()
