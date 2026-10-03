import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
import httpx
from app.core.config import Settings
from app.providers.usda import USDAFoodDataCentralProvider, match_key
from app.services.normalization import IngredientNormalizationService
from app.services.nutrition import NutritionService
from app.services.constraints import ConstraintService
from app.services.repair import eligible, score
from app.schemas.recipes import RecipeCandidate, RecipeGenerationRequest
from tests.test_nutrition import food

DATA = json.loads((Path(__file__).parent / 'fixtures/nutrition-diagnostic-records.json').read_text(encoding='utf-8'))
NORMALIZE = IngredientNormalizationService().normalize


class NutritionDisplaySupportTests(unittest.IsolatedAsyncioTestCase):
    def test_real_nutrient_mapping(self):
        oil = USDAFoodDataCentralProvider._parse_food(DATA['oil'], None)
        self.assertEqual(oil.nutrients_per_100g.fat, 93.7)
        self.assertEqual(oil.nutrient_ids['fat'], 1085)
        self.assertIsNone(oil.nutrients_per_100g.calories)
        broccoli = USDAFoodDataCentralProvider._parse_food(DATA['broccoli'], 'raw')
        self.assertEqual(broccoli.nutrients_per_100g.sugar, 1.48)
        self.assertEqual(broccoli.nutrient_ids['sugar'], 2000)

    def test_common_wording_preserves_identity(self):
        for name, expected in [('fresh garlic cloves, minced', 'garlic raw'), ('raw broccoli florets', 'broccoli flower clusters raw'), ('broccoli, fresh, raw, cut into florets', 'broccoli flower clusters raw'),
                ('boneless skinless chicken breasts, raw', 'boneless skinless chicken breast raw'),
                ('chopped onion, raw', 'onion raw'), ('uncooked brown rice', 'brown rice raw'),
                ('ground black pepper', 'black pepper'), ('olive oil', 'olive oil'), ('salt', 'salt')]:
            item = NORMALIZE(name, 10, 'g')
            self.assertEqual(match_key(' '.join(filter(None, [item.name, item.food_state]))), match_key(expected))
        self.assertNotEqual(match_key('fresh parsley'), match_key('dried parsley'))
        self.assertNotEqual(match_key('raw white rice'), match_key('cooked brown rice'))
        self.assertNotEqual(match_key('milk 1 percent'), match_key('milk 2 percent'))
        self.assertNotEqual(match_key('sea salt'), match_key('table salt'))

    async def test_mass_and_real_portions(self):
        for unit, amount, grams in [('g', 10, 10), ('kg', .1, 100), ('oz', 1, 28.349523125), ('lb', 1, 453.59237)]:
            self.assertAlmostEqual(NORMALIZE('garlic raw', amount, unit).grams, grams)
        provider = AsyncMock()
        provider.lookup.return_value = USDAFoodDataCentralProvider._parse_food(DATA['garlic_legacy'], 'raw')
        result = await NutritionService(provider).calculate([NORMALIZE('garlic raw, minced', 2, 'cloves')], 2)
        self.assertEqual(result.nutrition_sources[0].ingredient.grams, 6)
        provider.lookup.return_value = USDAFoodDataCentralProvider._parse_food(DATA['oil'], None)
        result = await NutritionService(provider).calculate([NORMALIZE('extra virgin olive oil', 25, 'ml')], 2)
        self.assertAlmostEqual(result.nutrition_sources[0].ingredient.grams, 22.675)
        self.assertAlmostEqual(result.calculated_nutrition.per_serving.fat, 22.675 * .937 / 2)
        for unit in ['breast', 'egg', 'slice']:
            result = await NutritionService(provider).calculate([NORMALIZE('extra virgin olive oil', 1, unit)], 1)
            self.assertEqual(result.nutrition_sources[0].status, 'unconvertible')

    async def test_full_partial_and_repair_constraint_safety(self):
        # Synthetic arithmetic over the six common ingredient identities.
        names = ['chicken breast raw', 'broccoli raw', 'olive oil', 'garlic raw', 'table salt', 'black pepper']
        provider = AsyncMock(); provider.lookup.return_value = food(sugar=2)
        ingredients = [NORMALIZE(n, 100, 'g') for n in names]
        full = await NutritionService(provider).calculate(ingredients, 2)
        self.assertEqual(full.calculated_nutrition.per_serving.calories, 300)
        self.assertEqual(full.calculated_nutrition.per_serving.sugar, 6)
        provider.lookup.side_effect = [food(sugar=2)] * 5 + [None]
        partial = await NutritionService(provider).calculate(ingredients, 2)
        self.assertEqual(partial.calculated_nutrition.known_per_serving.calories, 250)
        self.assertIsNone(partial.calculated_nutrition.per_serving.calories)
        self.assertEqual(partial.calculated_nutrition.coverage['calories'], 5)
        self.assertEqual(partial.nutrition_status, 'partial')
        raw = DATA['baseline']['recipe']
        recipe = RecipeCandidate.model_validate({k: raw[k] for k in RecipeCandidate.model_fields})
        request = RecipeGenerationRequest(selected_ingredients=['chicken'], calorie_target=300, protein_target=1)
        engine = ConstraintService()
        full = engine.validate(request, recipe, full)
        partial = engine.validate(request, recipe, partial)
        self.assertTrue(all(r.passed is None for r in partial.constraint_results))
        self.assertFalse(eligible(recipe, recipe, full, partial))
        self.assertGreater(score(partial), score(full))

    async def test_exact_legacy_can_improve_incomplete_foundation(self):
        def handler(request):
            if request.url.path.endswith('/search'):
                return httpx.Response(200, json={'foods': [{k: DATA[name][k] for k in ['fdcId','dataType','description']}
                    for name in ['garlic_foundation', 'garlic_legacy']]})
            body = DATA['garlic_legacy'] if request.url.path.endswith('/169230') else DATA['garlic_foundation']
            return httpx.Response(200, json=body)
        provider = USDAFoodDataCentralProvider(Settings(usda_api_key='test-only'), httpx.MockTransport(handler))
        chosen = await provider.lookup(NORMALIZE('fresh garlic cloves', 2, 'cloves'))
        self.assertEqual(chosen.food_id, '169230')
        self.assertIsNotNone(chosen.nutrients_per_100g.calories)

    async def test_refinement_failure_keeps_valid_foundation(self):
        def handler(request):
            if request.url.path.endswith('/search'):
                return httpx.Response(200, json={'foods': [{k: DATA[name][k] for k in ['fdcId','dataType','description']}
                    for name in ['garlic_foundation', 'garlic_legacy']]})
            if request.url.path.endswith('/169230'):
                raise httpx.ConnectError('test transport failure')
            return httpx.Response(200, json=DATA['garlic_foundation'])
        provider = USDAFoodDataCentralProvider(Settings(usda_api_key='test-only'), httpx.MockTransport(handler))
        chosen = await provider.lookup(NORMALIZE('garlic raw', 2, 'cloves'))
        self.assertEqual(chosen.food_id, '1104647')


class RecordedSelectionPolishTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_unspecified_garlic_does_not_acquire_raw_state(self):
        recorded = json.loads((Path(__file__).parent / 'fixtures/nutrition-polish-live.json').read_text(encoding='utf-8'))
        event = next(e for e in recorded['http_events'] if e.get('query') == 'garlic')
        calls = []
        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200, json={'foods': [{'fdcId': c['food_id'], 'description': c['description'], 'dataType': c['data_type']}
                for c in event['candidates']]})
        provider = USDAFoodDataCentralProvider(Settings(usda_api_key='test-only'), httpx.MockTransport(handler))
        self.assertIsNone(await provider.lookup(NORMALIZE('garlic cloves, minced', 15, 'g')))
        self.assertEqual(len(calls), 1)

    async def test_real_extra_virgin_record_does_not_borrow_generic_oil_macros(self):
        recorded = json.loads((Path(__file__).parent / 'fixtures/nutrition-polish-live.json').read_text(encoding='utf-8'))
        search = next(e for e in recorded['http_events'] if e.get('query') == 'extra oil olive virgin')
        detail = next(e for e in recorded['http_events'] if e.get('food_id') == '748608')
        def handler(request):
            if request.url.path.endswith('/search'):
                return httpx.Response(200, json={'foods': [{'fdcId': c['food_id'], 'description': c['description'], 'dataType': c['data_type']}
                    for c in search['candidates']]})
            return httpx.Response(200, json={'fdcId': 748608, 'description': detail['description'], 'dataType': detail['data_type'],
                'foodNutrients': [{'nutrient': {'id': n['id'], 'name': n['name'], 'unitName': n['unit']}, 'amount': n['amount']}
                    for n in detail['nutrients']]})
        provider = USDAFoodDataCentralProvider(Settings(usda_api_key='test-only'), httpx.MockTransport(handler))
        chosen = await provider.lookup(NORMALIZE('olive oil, extra virgin', 28, 'g'))
        self.assertEqual(chosen.food_id, '748608')
        self.assertEqual(chosen.nutrients_per_100g.fat, 93.7)
        self.assertEqual(chosen.nutrient_ids['fat'], 1085)
        self.assertIsNone(chosen.nutrients_per_100g.calories)
