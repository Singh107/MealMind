import json
import unittest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.core.errors import GenerationError
from app.main import create_app
from app.api.routes.recipes import get_recipe_service
from app.schemas.recipes import RecipeCandidate, RecipeGenerationRequest
from app.schemas.repair import RecipeRepairRequest
from app.services.recipes import RecipeService
from app.services.repair import RecipeRepairService, score
from app.services.nutrition import NutritionService
from tests.test_nutrition import food
from tests.test_recipes import FIXTURE


def candidate(quantity=600, name='Broccoli', protein=1):
    return RecipeCandidate.model_validate(FIXTURE | {'ingredients': [{'name': name, 'quantity': quantity, 'unit': 'g'}],
        'servings': 1, 'nutrition': {'calories': 490, 'protein': protein, 'carbohydrates': 1, 'fat': 1}})


class RepairTests(unittest.IsolatedAsyncioTestCase):
    def setup_service(self, proposals, **options):
        self.ai = AsyncMock()
        self.ai.repair.side_effect = [p.model_dump_json() if isinstance(p, RecipeCandidate) else p for p in proposals]
        self.food = AsyncMock()
        self.food.lookup.return_value = food()
        return RecipeRepairService(self.ai, NutritionService(self.food), **options)

    async def run_repair(self, proposals, original=None, options=None, **constraints):
        service = self.setup_service(proposals, **(options or {}))
        request = RecipeGenerationRequest(selected_ingredients=['Broccoli'], servings=1, **constraints)
        return await service.repair(RecipeRepairRequest(recipe=original or candidate(), constraints=request), 'test')

    async def test_no_repair_needed(self):
        r = await self.run_repair([], calorie_target=700)
        self.assertEqual(r.repair_status, 'not_needed'); self.ai.repair.assert_not_called()

    async def test_calorie_success_original_and_changes(self):
        r = await self.run_repair([candidate(490)], calorie_target=500)
        self.assertEqual((r.repair_status, r.repair_attempts), ('repaired', 1))
        self.assertEqual(r.original_recipe.ingredients[0].quantity, 600)
        self.assertEqual(r.after_intelligence.calculated_nutrition.per_serving.calories, 490)
        self.assertEqual(r.changes[0].before, '600 g'); self.assertEqual(r.changes[0].after, '490 g')
        self.assertNotEqual(r.original_recipe.recipe_version_id, r.final_recipe.recipe_version_id)
        self.assertEqual(self.food.lookup.await_count, 2)

    async def test_protein_success(self):
        r = await self.run_repair([candidate(700)], protein_target=65)
        self.assertEqual(r.repair_status, 'repaired')
        self.assertEqual(r.after_intelligence.calculated_nutrition.per_serving.protein, 70)

    async def test_multiple_failed_constraints(self):
        r = await self.run_repair([candidate(400)], calorie_target=450, fat_target=21)
        self.assertEqual(r.repair_status, 'repaired')
        data = self.ai.repair.call_args.args[0]
        self.assertEqual(len(data['failed_constraints']), 2)
        self.assertNotIn('nutrition_sources', data)
        self.assertNotIn('id', data['current_recipe'])

    async def test_ai_490_is_calculated_540(self):
        r = await self.run_repair([candidate(540), candidate(550)], calorie_target=500)
        self.assertEqual(r.final_recipe.nutrition.calories, 490)
        self.assertEqual(r.after_intelligence.calculated_nutrition.per_serving.calories, 540)
        self.assertEqual(r.repair_status, 'partially_repaired')
        self.assertEqual(r.remaining_failed_constraints[0].actual, 540)

    async def test_attempt_limit_and_tie_keeps_earliest(self):
        r = await self.run_repair([candidate(550), candidate(550)], calorie_target=500)
        self.assertEqual(r.repair_attempts, 2); self.assertEqual(self.ai.repair.await_count, 2)
        self.assertEqual(r.final_recipe.ingredients[0].quantity, 550)

    async def test_no_improvement_preserves_original(self):
        r = await self.run_repair([candidate(700), candidate(800)], calorie_target=500)
        self.assertEqual(r.repair_status, 'failed')
        self.assertEqual(r.original_recipe, r.final_recipe)

    async def test_hard_diet_rejects_macro_improvement(self):
        r = await self.run_repair([candidate(100, 'Chicken breast')]*2, calorie_target=500, dietary_preferences=['vegan'])
        self.assertEqual(r.repair_status, 'failed')
        self.assertEqual(r.failure_code, 'unsafe_or_unverifiable_repair')

    async def test_exclusion_rejects_macro_improvement(self):
        r = await self.run_repair([candidate(100, 'Olive oil')]*2, calorie_target=500, excluded_ingredients=['olive oil'])
        self.assertEqual(r.repair_status, 'failed')

    async def test_allergy_rejects_macro_improvement(self):
        r = await self.run_repair([candidate(100, 'Peanuts')]*2, calorie_target=500, allergies=['peanuts'])
        self.assertEqual(r.repair_status, 'failed')

    async def test_unknown_allergy_allows_quantity_only_never_certifies(self):
        r = await self.run_repair([candidate(400)]*2, calorie_target=500, allergies=['peanuts'])
        self.assertEqual(r.repair_status, 'partially_repaired')
        self.assertEqual(r.after_intelligence.constraint_results[-1].status, 'unknown')

    async def test_unknown_hard_rejects_new_ingredients(self):
        r = await self.run_repair([candidate(100, 'Garlic')]*2, calorie_target=500, allergies=['peanuts'])
        self.assertEqual(r.repair_status, 'failed')

    async def test_malformed_and_protected_fields(self):
        for proposal in ['not json', candidate(100).model_copy(update={'servings': 2}).model_dump_json(),
                         json.dumps(candidate(100).model_dump() | {'validation_status': 'verified'})]:
            r = await self.run_repair([proposal], calorie_target=500)
            self.assertEqual(r.failure_code, 'invalid_repair_output')
            self.assertEqual(r.original_recipe, r.final_recipe)

    async def test_provider_unavailable(self):
        r = await self.run_repair([GenerationError('provider_failure', 'private message')], calorie_target=500)
        self.assertEqual(r.repair_status, 'failed'); self.assertEqual(r.repair_attempts, 1)
        self.assertIn('temporarily unavailable', r.message); self.assertNotIn('private', r.message)
        self.assertEqual(r.before_intelligence, r.after_intelligence)

    async def test_improvement_survives_later_provider_failure(self):
        r = await self.run_repair([candidate(550), GenerationError('provider_failure', 'private')], calorie_target=500)
        self.assertEqual(r.repair_status, 'partially_repaired')
        self.assertEqual(r.final_recipe.ingredients[0].quantity, 550)

    async def test_unknown_nutrition_cannot_win(self):
        service = self.setup_service([candidate(100), candidate(100)])
        self.food.lookup.side_effect = [food(), None, None]
        r = await service.repair(RecipeRepairRequest(recipe=candidate(), constraints=RecipeGenerationRequest(
            selected_ingredients=['Broccoli'], servings=1, calorie_target=500)), 'test')
        self.assertEqual(r.repair_status, 'failed')

    async def test_zero_target_scoring_is_finite(self):
        r = await self.run_repair([candidate(100), candidate(200)], calorie_target=0)
        self.assertEqual(score(r.after_intelligence), (0, 100))

    async def test_disabled_attempts(self):
        r = await self.run_repair([], calorie_target=500, options={'max_attempts': 0})
        self.assertEqual(r.repair_attempts, 0); self.assertEqual(r.repair_status, 'failed')

    async def test_cooking_time_revalidated(self):
        original = candidate().model_copy(update={'cook_time': 60, 'total_time': 60 + candidate().prep_time})
        proposal = candidate().model_copy(update={'cook_time': 15, 'total_time': 15 + candidate().prep_time})
        r = await self.run_repair([proposal], original=original, max_cooking_time=20)
        self.assertEqual(r.repair_status, 'repaired')

    async def test_timeout_preserves_original(self):
        import asyncio
        service = self.setup_service([], timeout_seconds=.02)
        async def slow(_):
            await asyncio.sleep(1)
        self.ai.repair.side_effect = slow
        r = await service.repair(RecipeRepairRequest(recipe=candidate(), constraints=RecipeGenerationRequest(
            selected_ingredients=['Broccoli'], servings=1, calorie_target=500)), 'test')
        self.assertEqual(r.failure_code, 'repair_timeout'); self.assertEqual(r.original_recipe, r.final_recipe)


class RepairRouteTests(unittest.TestCase):
    def test_route_uses_real_services_with_mock_providers(self):
        ai, foods = AsyncMock(), AsyncMock()
        ai.repair.return_value = candidate(400).model_dump_json(); foods.lookup.return_value = food()
        app = create_app(Settings())
        app.dependency_overrides[get_recipe_service] = lambda: RecipeService(ai, nutrition_service=NutritionService(foods))
        with TestClient(app) as client:
            result = client.post('/api/recipes/repair', json={'recipe': candidate().model_dump(),
                'constraints': {'selected_ingredients': ['Broccoli'], 'servings': 1, 'calorie_target': 500}})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['repair_status'], 'repaired')


class RepairConfigurationTests(unittest.TestCase):
    def test_limits_and_environment_override(self):
        import os
        from unittest.mock import patch
        from pydantic import ValidationError
        from app.core.config import get_settings
        self.assertEqual(Settings().max_repair_attempts, 2)
        with self.assertRaises(ValidationError):
            Settings(max_repair_attempts=3)
        with patch.dict(os.environ, {'MAX_REPAIR_ATTEMPTS': '1'}), patch('app.core.config.load_dotenv'):
            get_settings.cache_clear()
            try: self.assertEqual(get_settings().max_repair_attempts, 1)
            finally: get_settings.cache_clear()

    def test_client_verification_metadata_is_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RecipeRepairRequest.model_validate({'recipe': candidate().model_dump(),
                'constraints': {'selected_ingredients': ['Broccoli']}, 'calculated_nutrition': {'calories': 1}})


class RepairProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_repair_uses_structured_contract(self):
        import httpx
        from app.providers.gemini import GeminiRecipeProvider
        captured = []
        def handler(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP',
                'content': {'parts': [{'text': candidate(400).model_dump_json()}]}}]})
        provider = GeminiRecipeProvider(Settings(gemini_api_key='test-only'), httpx.MockTransport(handler))
        raw = await provider.repair({'failed_constraints': [{'constraint': 'maximum_calories'}]})
        self.assertEqual(RecipeCandidate.model_validate_json(raw).ingredients[0].quantity, 400)
        self.assertEqual(captured[0]['generationConfig']['responseMimeType'], 'application/json')
        self.assertIn('Target ONLY', captured[0]['systemInstruction']['parts'][0]['text'])
