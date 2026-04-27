import unittest

from src.backend.Raven_graph import EnricherOutput, raven_graph
from src.backend.data.prompt.enricher import ENRICHER_PROMPT


class EnricherContractTest(unittest.TestCase):
    def test_prompt_has_production_constraints(self) -> None:
        required_fragments = [
            "Preserve the user's exact target as the first query",
            "Decide how many queries are needed",
            "Also output key_words",
            "cheap title relevance filtering",
            "key_words is extraction, not generation",
            "original target only",
            "Every key_word must be traceable to a word in the user's original query",
            "Original-query membership is necessary but not sufficient",
            "The word tools is forbidden in key_words",
            "usually be 3-5 target-specific search anchors",
            "Use only words from the original target",
            "broad filter-poison words",
            "key_words should look like grow, youtube, channel",
            "Do not include tools or small",
            "Bad key_words: reddit, complaints, project, management, tools, small, agencies",
            "Good key_words: reddit, complaints, project, management, agencies",
            "Do not create fake proper nouns",
            "failure mode",
            "tools, numbers, metrics",
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
