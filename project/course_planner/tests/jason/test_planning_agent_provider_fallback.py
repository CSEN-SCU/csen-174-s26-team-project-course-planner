import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents import planning_agent


class JasonPlanningAgentProviderFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset module-level client cache between tests.
        planning_agent._client = None

    def tearDown(self) -> None:
        planning_agent._client = None

    def test_prefers_gemini_api_key_over_google_api_key(self) -> None:
        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "gemini-key", "GOOGLE_API_KEY": "google-key"},
            clear=True,
        ):
            with patch.object(planning_agent.genai, "Client") as client_cls:
                planning_agent._get_client()
                client_cls.assert_called_once_with(api_key="gemini-key")

    def test_falls_back_to_secondary_model_after_transient_primary_failures(self) -> None:
        fake_response = SimpleNamespace(
            text='{"recommended":[{"course":"CSE 130","category":"Core","units":4,"reason":"Strong fit"}],"total_units":4,"advice":"Take CSE 130 first."}'
        )
        call_models: list[str] = []
        attempts = {"primary": 0}

        def fake_generate_content(*, model, contents, config):
            del contents, config
            call_models.append(model)
            if model == "primary":
                attempts["primary"] += 1
                raise Exception("503 service unavailable")
            if model == "fallback":
                return fake_response
            raise AssertionError(f"Unexpected model attempted: {model}")

        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "primary"}, clear=True):
            with patch.object(planning_agent, "_get_client", return_value=fake_client):
                with patch.object(planning_agent, "FALLBACK_MODELS", ("fallback",)):
                    with patch.object(planning_agent.time, "sleep", return_value=None):
                        result = planning_agent.run_planning_agent(
                            [{"course": "CSE 130", "category": "Core", "units": 4}],
                            "balanced workload",
                        )

        self.assertEqual(attempts["primary"], 3)
        self.assertEqual(call_models, ["primary", "primary", "primary", "fallback"])
        self.assertEqual(result["recommended"][0]["course"], "CSE 130")


if __name__ == "__main__":
    unittest.main()
