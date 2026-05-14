import unittest
from unittest.mock import patch

from agents import gemini_client
from agents.requirement_agent import run_requirement_agent


class RequirementAgentClientTests(unittest.TestCase):
    def setUp(self) -> None:
        gemini_client.reset_client_for_tests()

    def tearDown(self) -> None:
        gemini_client.reset_client_for_tests()

    def test_missing_api_key_raises_before_calling_model(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                run_requirement_agent(b"%PDF-1.4", ["CSEN 174"])
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
