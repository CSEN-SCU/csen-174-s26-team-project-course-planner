import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents import planning_agent


class JasonPlanningAgentFutureFeaturesRedTests(unittest.TestCase):
    def setUp(self) -> None:
        planning_agent._client = None

    def tearDown(self) -> None:
        planning_agent._client = None

    def _fake_client_with_text(self, text: str):
        response = SimpleNamespace(text=text)

        def fake_generate_content(*, model, contents, config):
            del model, contents, config
            return response

        return SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))

    def test_adds_provider_metadata_block_to_response(self) -> None:
        fake_client = self._fake_client_with_text(
            '{"recommended":[{"course":"CSE 130","category":"Core","units":4,"reason":"Good fit"}],"total_units":4,"advice":"Balanced plan."}'
        )

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-2.5-flash"}, clear=True):
            with patch.object(planning_agent, "_get_client", return_value=fake_client):
                result = planning_agent.run_planning_agent(
                    [{"course": "CSE 130", "category": "Core", "units": 4}],
                    "balanced workload",
                )

        # RED target: API should attach provider/model/fallback/requestId metadata.
        self.assertIn("meta", result)
        self.assertIn("provider", result["meta"])
        self.assertIn("model", result["meta"])
        self.assertIn("fallback_used", result["meta"])
        self.assertIn("request_id", result["meta"])

    def test_backfills_course_alternatives_when_model_omits_them(self) -> None:
        fake_client = self._fake_client_with_text(
            '{"recommended":[{"course":"CSE 130","category":"Core","units":4,"reason":"Good fit"}],"total_units":4,"advice":"Balanced plan."}'
        )

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            with patch.object(planning_agent, "_get_client", return_value=fake_client):
                result = planning_agent.run_planning_agent(
                    [{"course": "CSE 130", "category": "Core", "units": 4}],
                    "balanced workload",
                )

        # RED target: every course recommendation should expose alternatives for swap UI.
        self.assertIn("alternatives", result["recommended"][0])
        self.assertIsInstance(result["recommended"][0]["alternatives"], list)

    def test_adds_plan_warnings_for_overloaded_unit_count(self) -> None:
        fake_client = self._fake_client_with_text(
            '{"recommended":[{"course":"CSE 130","category":"Core","units":5,"reason":"Required"},{"course":"CSE 160","category":"Core","units":5,"reason":"Required"},{"course":"CSE 170","category":"Elective","units":5,"reason":"Elective"},{"course":"CSE 180","category":"Elective","units":5,"reason":"Elective"}],"total_units":20,"advice":"You can do this."}'
        )

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            with patch.object(planning_agent, "_get_client", return_value=fake_client):
                result = planning_agent.run_planning_agent(
                    [{"course": "CSE 130", "category": "Core", "units": 5}],
                    "finish as quickly as possible",
                )

        # RED target: backend should add warnings metadata for risky schedules.
        self.assertIn("warnings", result)
        self.assertGreater(len(result["warnings"]), 0)


if __name__ == "__main__":
    unittest.main()
