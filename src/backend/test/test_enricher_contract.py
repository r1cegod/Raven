import unittest

from src.backend.data.prompt.enricher import ENRICHER_PROMPT
from src.backend.raven_graph import raven_graph
from src.backend.youtube_ranker_tier1 import EnricherOutput


class EnricherContractTest(unittest.TestCase):
    def test_prompt_has_production_constraints(self) -> None:
        required_fragments = [
            "Decide how many queries are needed",
            "The request is not itself a search query",
            "Also output key_words",
            "cheap title relevance filtering",
            "key_words is extraction, not generation",
            "request only",
            "The word tools is forbidden in key_words",
            "usually be 3-5 request-specific search anchors",
            "broad filter-poison words",
            "youtube, channel, growth, audience, distribution",
            "Do not create fake proper nouns",
            "failure mode",
            "tools, workflows, numbers",
        ]

        for fragment in required_fragments:
            self.assertIn(fragment, ENRICHER_PROMPT)

    def test_graph_exists(self) -> None:
        self.assertIsNotNone(raven_graph)

    def test_structured_output_allows_llm_to_choose_query_count(self) -> None:
        output = EnricherOutput(queries=["how to find leads"], key_words=["lead"])
        self.assertEqual(output.queries, ["how to find leads"])
        self.assertEqual(output.key_words, ["lead"])

    def test_structured_output_requires_key_words(self) -> None:
        with self.assertRaises(Exception):
            EnricherOutput(queries=["how to find leads"])


if __name__ == "__main__":
    unittest.main()
