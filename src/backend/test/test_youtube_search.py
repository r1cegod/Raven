import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from src.backend.search import youtube_search


class YouTubeSearchTest(unittest.TestCase):
    def test_search_call_sends_published_after_to_search_list(self) -> None:
        opened_urls: list[str] = []

        class FakeResponse:
            status = 200

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"items": []}'

        def fake_urlopen(request, timeout: int = 15):  # noqa: ANN001
            opened_urls.append(request.full_url)
            return FakeResponse()

        fixed_now = datetime(2026, 5, 2, 8, 0, 0, tzinfo=timezone.utc)

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001
                if tz is None:
                    return fixed_now.replace(tzinfo=None)
                return fixed_now.astimezone(tz)

        with (
            patch.object(youtube_search, "api_get", return_value="test-key"),
            patch.object(youtube_search.urllib.request, "urlopen", side_effect=fake_urlopen),
            patch.object(youtube_search, "datetime", FixedDatetime),
        ):
            response = youtube_search.searchs_call(
                "how to grow a youtube channel",
                max_results=100,
                duration="long",
                max_age_days=30,
                language="en",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(opened_urls), 1)
        params = parse_qs(urlparse(opened_urls[0]).query)
        self.assertEqual(params["publishedAfter"], ["2026-04-02T08:00:00Z"])
        self.assertEqual(params["relevanceLanguage"], ["en"])
        self.assertEqual(params["maxResults"], ["50"])
        self.assertEqual(params["videoDuration"], ["long"])


if __name__ == "__main__":
    unittest.main()
