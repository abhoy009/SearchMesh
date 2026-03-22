import unittest

from src.app.models import SearchResult, TurnResult


class TestModels(unittest.TestCase):
    def test_search_result_defaults(self) -> None:
        result = SearchResult(title="t", url="https://example.com")
        self.assertEqual(result.content, "")
        self.assertEqual(result.source, "unknown")

    def test_turn_result_defaults(self) -> None:
        turn = TurnResult(assistant_text="ok", user_input="hi")
        self.assertFalse(turn.context_used)
        self.assertFalse(turn.metrics.search_used)


if __name__ == "__main__":
    unittest.main()
