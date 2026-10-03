import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.core.config import Settings, get_settings
from app.main import create_app
from app.providers.dev_fixture import DevelopmentRecipeProvider
from app.schemas.recipes import RecipeCandidate, RecipeGenerationRequest
from tests.test_nutrition import food


class DevelopmentFixtureTests(unittest.TestCase):
    def test_disabled_by_default_and_rejected_in_production(self):
        self.assertFalse(Settings().dev_mock_ai)
        with self.assertRaises(ValidationError):
            Settings(dev_mock_ai=True)
        self.assertTrue(Settings(dev_mock_ai=True, mealmind_environment='development').dev_mock_ai)

    def test_startup_reports_only_safe_provider_mode(self):
        for settings, mode in [(Settings(), 'Gemini'),
                (Settings(dev_mock_ai=False, mealmind_environment='development'), 'Gemini'),
                (Settings(dev_mock_ai=True, mealmind_environment='development'), 'Development fixture')]:
            with self.assertLogs('uvicorn.error', level='INFO') as captured:
                create_app(settings)
            self.assertEqual(captured.output, ['INFO:uvicorn.error:Recipe provider: ' + mode])

    def test_explicit_environment_flags(self):
        import os
        with patch.dict(os.environ, {'MEALMIND_DEV_MOCK_AI': 'true', 'MEALMIND_ENVIRONMENT': 'development'}), patch('app.core.config.load_dotenv'):
            get_settings.cache_clear()
            try: self.assertTrue(get_settings().dev_mock_ai)
            finally: get_settings.cache_clear()

    def test_real_routes_generate_and_repair_fixture_with_independent_nutrition(self):
        app = create_app(Settings(dev_mock_ai=True, mealmind_environment='development'))
        with patch('app.providers.usda.USDAFoodDataCentralProvider.lookup', new=AsyncMock(return_value=food())), \
             patch('app.providers.gemini.GeminiRecipeProvider.generate', new=AsyncMock()) as gemini, TestClient(app) as client:
            preferences = {'selected_ingredients': ['Broccoli'], 'servings': 2, 'max_cooking_time': 15}
            generated = client.post('/api/recipes/generate', json=preferences)
            self.assertEqual(generated.status_code, 200)
            data = generated.json()
            self.assertEqual(data['metadata']['provider'], 'development-fixture')
            self.assertIn('[DEV FIXTURE]', data['recipe']['title'])
            self.assertIsNone(data['recipe']['nutrition']['calories'])
            self.assertIsNotNone(data['calculated_nutrition']['per_serving']['calories'])
            self.assertEqual(data['constraint_results'][0]['status'], 'failed')
            content = {k: v for k, v in data['recipe'].items() if k in RecipeCandidate.model_fields}
            repaired = client.post('/api/recipes/repair', json={'recipe': content, 'constraints': preferences})
            self.assertEqual(repaired.status_code, 200)
            result = repaired.json()
            self.assertEqual(result['repair_status'], 'repaired')
            self.assertEqual(result['original_recipe']['cook_time'], 30)
            self.assertEqual(result['final_recipe']['cook_time'], 10)
            self.assertTrue(result['changes'])
            gemini.assert_not_called()

    def test_default_route_keeps_gemini(self):
        from app.core.errors import GenerationError
        app = create_app(Settings())
        with patch('app.providers.gemini.GeminiRecipeProvider.generate', new=AsyncMock(side_effect=GenerationError('provider_failure', 'Unavailable'))), TestClient(app) as client:
            r = client.post('/api/recipes/generate', json={'selected_ingredients': ['Broccoli']})
            self.assertEqual(r.status_code, 502)
            self.assertEqual(r.json()['error']['code'], 'provider_failure')


class DevelopmentProposalTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_proposals_use_strict_schema_and_only_targeted_changes(self):
        provider = DevelopmentRecipeProvider()
        request = RecipeGenerationRequest(selected_ingredients=['Broccoli'], servings=2)
        original = RecipeCandidate.model_validate_json(await provider.generate(request))
        repaired = RecipeCandidate.model_validate_json(await provider.repair({'current_recipe': original.model_dump(),
            'failed_constraints': [{'constraint': 'maximum_fat'}], 'original_preferences': request.model_dump()}))
        self.assertEqual(repaired.ingredients[1].quantity, 20)
        self.assertEqual(repaired.cook_time, original.cook_time)
