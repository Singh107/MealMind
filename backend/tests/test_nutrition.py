import asyncio
import json
import unittest
from unittest.mock import AsyncMock
import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.api.routes.recipes import get_recipe_service
from app.core.config import Settings
from app.main import create_app
from app.providers.nutrition import NutritionProviderError
from app.providers.usda import USDAFoodDataCentralProvider
from app.schemas.intelligence import FoodPortion, FoodRecord, NutrientValues
from app.schemas.recipes import RecipeCandidate, RecipeGenerationRequest
from app.services.constraints import ConstraintService
from app.services.normalization import IngredientNormalizationService
from app.services.nutrition import NutritionService
from app.services.nutrition_cache import CachedNutritionProvider, InMemoryFoodCache
from app.services.recipes import RecipeService
from tests.test_recipes import FIXTURE

NORMALIZER = IngredientNormalizationService()


def food(**changes):
    # Synthetic arithmetic fixture, not claimed to be USDA's measured values.
    return FoodRecord(food_id='123', description='Broccoli, raw', data_type='Foundation',
        retrieved_at='2026-09-11T00:00:00+00:00', food_state='raw',
        nutrients_per_100g=NutrientValues(**({'calories': 100, 'protein': 10, 'carbohydrates': 15,
                                             'fat': 5, 'fiber': 2, 'sodium': 20} | changes)))


class NormalizationTests(unittest.TestCase):
    def test_common_mass_units_and_decimals(self):
        for unit, quantity, grams in [('grams', '1.5', 1.5), ('kg', '.25', 250), ('oz', 1, 28.349523125),
                                     ('lb', 1, 453.59237), ('mg', 1000, 1)]:
            with self.subTest(unit=unit):
                result = NORMALIZER.normalize('Broccoli, raw, chopped', quantity, unit)
                self.assertEqual(result.name, 'Broccoli')
                self.assertEqual(result.canonical_name, 'broccoli')
                self.assertEqual(result.preparation, 'chopped')
                self.assertEqual(result.food_state, 'raw')
                self.assertAlmostEqual(result.grams, grams)
                self.assertEqual(result.status, 'normalized')

    def test_fractions_and_natural_text(self):
        for text, quantity, unit, name in [('2 tbsp olive oil', 2, 'tbsp', 'olive oil'),
                ('half a cup of Greek yogurt', .5, 'cup', 'Greek yogurt'),
                ('1 1/2 cups lentils', 1.5, 'cup', 'lentils'), ('1½ cups lentils', 1.5, 'cup', 'lentils'),
                ('1/4 cup lentils', .25, 'cup', 'lentils'), ('.5 cup lentils', .5, 'cup', 'lentils'),
                ('2 large chicken breasts', 2, 'large', 'chicken breasts')]:
            with self.subTest(text=text):
                result = NORMALIZER.normalize(text)
                self.assertEqual((result.quantity, result.normalized_unit, result.name), (quantity, unit, name))
                self.assertIsNone(result.grams)
                self.assertEqual(result.status, 'needs_conversion')

    def test_missing_invalid_and_unsupported_measurements(self):
        for name, quantity, unit in [('salt to taste', None, None), ('2 handfuls spinach', None, None), ('broccoli', 2, 'handfuls'),
                                    ('broccoli', '1/0', 'g'), ('broccoli', -2, 'g'), ('broccoli', True, 'g'),
                                    ('raw cooked rice', 100, 'g')]:
            with self.subTest(name=name, quantity=quantity):
                result = NORMALIZER.normalize(name, quantity, unit)
                self.assertEqual(result.status, 'unresolved')
                self.assertIsNone(result.grams)

    def test_unknown_names_not_silently_mapped(self):
        result = NORMALIZER.normalize('mystery sauce', 10, 'g')
        self.assertIsNone(result.canonical_name)
        self.assertEqual(result.grams, 10)


class NutritionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = AsyncMock()
        self.provider.lookup.return_value = food()
        self.service = NutritionService(self.provider)

    async def test_scaling_totals_and_per_serving(self):
        report = await self.service.calculate([NORMALIZER.normalize('raw broccoli', 250, 'g'),
                                               NORMALIZER.normalize('raw carrots', 150, 'g')], 4)
        self.assertEqual(report.nutrition_status, 'verified')
        self.assertEqual(report.calculated_nutrition.totals.calories, 400)
        self.assertEqual(report.calculated_nutrition.per_serving.protein, 10)
        self.assertEqual(report.calculated_nutrition.totals.sodium, 80)
        self.assertEqual(report.calculated_nutrition.coverage['calories'], 2)

    async def test_unmatched_ingredient_never_creates_complete_totals(self):
        self.provider.lookup.side_effect = [food(), None]
        report = await self.service.calculate([NORMALIZER.normalize('raw broccoli', 100, 'g'),
                                               NORMALIZER.normalize('mystery sauce', 10, 'g')], 2)
        self.assertEqual(report.nutrition_status, 'partial')
        self.assertIsNone(report.calculated_nutrition.per_serving.calories)
        self.assertEqual(report.calculated_nutrition.known_per_serving.calories, 50)
        self.assertEqual(len(report.unmatched_ingredients), 1)

    async def test_one_missing_nutrient_is_null_not_zero(self):
        self.provider.lookup.return_value = food(protein=None, sodium=None)
        report = await self.service.calculate([NORMALIZER.normalize('raw broccoli', 100, 'g')], 1)
        self.assertEqual(report.nutrition_status, 'partial')
        self.assertIsNone(report.calculated_nutrition.per_serving.protein)
        self.assertEqual(report.calculated_nutrition.per_serving.calories, 100)

    async def test_missing_optional_nutrient_preserves_core_verification(self):
        self.provider.lookup.return_value = food(sodium=None)
        report = await self.service.calculate([NORMALIZER.normalize('raw broccoli', 100, 'g')], 1)
        self.assertEqual(report.nutrition_status, 'verified')
        self.assertIsNone(report.calculated_nutrition.per_serving.sodium)

    async def test_provider_failure_stops_further_network_calls(self):
        self.provider.lookup.side_effect = NutritionProviderError('offline')
        report = await self.service.calculate([NORMALIZER.normalize('raw broccoli', 100, 'g'),
                                               NORMALIZER.normalize('raw carrots', 100, 'g')], 2)
        self.assertEqual(report.nutrition_status, 'unavailable')
        self.provider.lookup.assert_awaited_once()
        self.assertIsNone(report.calculated_nutrition.known_totals.calories)

    async def test_timeout_retains_completed_ingredients(self):
        async def lookup(ingredient):
            if ingredient.name == 'carrots':
                await asyncio.sleep(.2)
            return food()
        self.provider.lookup.side_effect = lookup
        self.service.timeout_seconds = .01
        report = await self.service.calculate([NORMALIZER.normalize('raw broccoli', 100, 'g'),
                                               NORMALIZER.normalize('raw carrots', 100, 'g')], 1)
        self.assertEqual(report.nutrition_status, 'partial')
        self.assertEqual(report.calculated_nutrition.known_totals.calories, 100)

    async def test_portion_conversion_requires_unique_evidence(self):
        record = food()
        record.portions = [FoodPortion(unit='tbsp', amount=1, gram_weight=13.5, description='1 tbsp')]
        self.provider.lookup.return_value = record
        report = await self.service.calculate([NORMALIZER.normalize('olive oil', 2, 'tbsp')], 1)
        self.assertEqual(report.nutrition_sources[0].ingredient.grams, 27)
        self.assertIn('USDA FDC 123', report.nutrition_sources[0].ingredient.conversion_evidence)
        record.portions.append(FoodPortion(unit='tbsp', amount=1, gram_weight=15, description='1 tbsp'))
        report = await self.service.calculate([NORMALIZER.normalize('olive oil', 2, 'tbsp')], 1)
        self.assertEqual(report.nutrition_status, 'unavailable')
        self.assertEqual(report.nutrition_sources[0].status, 'unconvertible')

    async def test_no_generic_volume_to_grams_or_unknown_unit_guess(self):
        for name, unit in [('raw broccoli', 'cup'), ('raw broccoli', 'pinch')]:
            report = await self.service.calculate([NORMALIZER.normalize(name, 1, unit)], 1)
            self.assertIsNone(report.calculated_nutrition.totals.calories)

    async def test_repeated_food_lookup_deduplicated(self):
        await self.service.calculate([NORMALIZER.normalize('raw broccoli', 100, 'g')] * 2, 2)
        self.provider.lookup.assert_awaited_once()


class ConstraintTests(unittest.IsolatedAsyncioTestCase):
    async def test_parent_identity_does_not_certify_specific_exclusion(self):
        result = await self.report({'excluded_ingredients': ['chicken breast']}, ('chicken',))
        self.assertEqual(result.constraint_results[0].status, 'unknown')
        result = await self.report({'excluded_ingredients': ['chicken']}, ('raw chicken breast',))
        self.assertEqual(result.constraint_results[0].status, 'failed')

    async def report(self, request, ingredient_names=('raw broccoli',), provider_result=True):
        provider = AsyncMock()
        provider.lookup.return_value = food() if provider_result else None
        recipe = RecipeCandidate.model_validate(FIXTURE | {'ingredients': [
            {'name': name, 'quantity': 100, 'unit': 'g'} for name in ingredient_names], 'servings': 1})
        intelligence = await NutritionService(provider).calculate([NORMALIZER.normalize(i.name, i.quantity, i.unit) for i in recipe.ingredients], 1)
        return ConstraintService().validate(RecipeGenerationRequest(selected_ingredients=['broccoli'], **request), recipe, intelligence)

    async def test_numeric_pass_fail_inclusive_no_rounding(self):
        for request, expected in [({'calorie_target': 100}, True), ({'calorie_target': 99.999}, False),
                                 ({'protein_target': 10}, True), ({'protein_target': 10.001}, False),
                                 ({'carbs_target': 15}, True), ({'carbs_target': 14}, False),
                                 ({'fat_target': 5}, True), ({'fat_target': 4}, False)]:
            with self.subTest(request=request):
                result = await self.report(request)
                self.assertEqual(result.constraint_results[0].passed, expected)
                self.assertEqual(result.overall_constraint_status, 'passed' if expected else 'failed')

    async def test_ranges_and_cooking_time(self):
        report = await self.report({'calorie_range': {'minimum': 90, 'maximum': 110}, 'max_cooking_time': 25})
        self.assertTrue(all(r.passed for r in report.constraint_results))
        report = await self.report({'max_cooking_time': 24})
        self.assertEqual(report.overall_constraint_status, 'failed')

    async def test_exclusions_aliases_and_unknown_composites(self):
        report = await self.report({'excluded_ingredients': ['tomatoes']}, ('raw tomato',))
        self.assertFalse(report.constraint_results[0].passed)
        report = await self.report({'excluded_ingredients': ['mushrooms']}, ('mystery sauce',))
        self.assertIsNone(report.constraint_results[0].passed)

    async def test_allergy_conflict_and_uncertainty(self):
        report = await self.report({'allergies': ['dairy']}, ('greek yogurt',))
        self.assertFalse(report.constraint_results[0].passed)
        report = await self.report({'allergies': ['dairy']})
        self.assertIsNone(report.constraint_results[0].passed)
        self.assertTrue(report.potential_allergen_warnings)

    async def test_diet_not_inferred_from_ai_tags(self):
        report = await self.report({'dietary_preferences': ['vegan']}, ('raw chicken breast',))
        self.assertFalse(report.constraint_results[0].passed)
        report = await self.report({'dietary_preferences': ['vegan']})
        self.assertTrue(report.constraint_results[0].passed)
        report = await self.report({'dietary_preferences': ['vegan']}, ('mystery sauce',))
        self.assertIsNone(report.constraint_results[0].passed)

    async def test_partial_data_cannot_pass_numeric_constraint(self):
        report = await self.report({'calorie_target': 500}, provider_result=False)
        self.assertIsNone(report.constraint_results[0].actual)
        self.assertIsNone(report.constraint_results[0].passed)
        self.assertEqual(report.overall_constraint_status, 'partially_verified')

    def test_invalid_ranges_rejected(self):
        for fields in [{'calorie_range': {'minimum': 600, 'maximum': 500}}, {'fat_range': {}},
                       {'carbs_target': 20, 'carbs_range': {'maximum': 30}}]:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                RecipeGenerationRequest(selected_ingredients=['broccoli'], **fields)


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_hit_expiry_eviction_and_state_separation(self):
        now = [0.0]
        cache = InMemoryFoodCache(ttl_seconds=10, max_entries=1, clock=lambda: now[0])
        provider = AsyncMock()
        provider.lookup.return_value = food()
        cached = CachedNutritionProvider(provider, cache)
        raw = NORMALIZER.normalize('raw broccoli', 100, 'g')
        await cached.lookup(raw)
        await cached.lookup(raw)
        self.assertEqual(provider.lookup.await_count, 1)
        await cached.lookup(NORMALIZER.normalize('cooked broccoli', 100, 'g'))
        await cached.lookup(raw)
        self.assertEqual(provider.lookup.await_count, 3)
        now[0] = 11
        await cached.lookup(raw)
        self.assertEqual(provider.lookup.await_count, 4)


class NutritionEndpointTests(unittest.TestCase):
    def test_calculation_is_additive_and_never_uses_llm_nutrients(self):
        ai = AsyncMock(name='ai')
        ai.name, ai.model = 'fixture', 'v1'
        ai.generate.return_value = json.dumps(FIXTURE)
        provider = AsyncMock()
        provider.lookup.return_value = food()
        service = RecipeService(ai, nutrition_service=NutritionService(provider))
        app = create_app(Settings())
        app.dependency_overrides[get_recipe_service] = lambda: service
        with TestClient(app) as client:
            r = client.post('/api/recipes/generate', json={'selected_ingredients': ['Lentils'], 'protein_target': 40})
            self.assertEqual(r.status_code, 200, r.text)
            data = r.json()
            self.assertEqual(data['recipe']['nutrition']['calories'], 210)
            self.assertEqual(data['calculated_nutrition']['per_serving']['calories'], 125)
            self.assertEqual(data['nutrition_status'], 'verified')
            self.assertEqual(data['overall_constraint_status'], 'failed')
            self.assertEqual(len(data['nutrition_sources']), 2)
            provider.lookup.side_effect = NutritionProviderError('offline')
            r = client.post('/api/recipes/generate', json={'selected_ingredients': ['Lentils'], 'protein_target': 40})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()['nutrition_status'], 'unavailable')
            self.assertEqual(r.json()['overall_constraint_status'], 'partially_verified')
            self.assertEqual(client.post('/api/recipes/generate', json={'selected_ingredients': []}).status_code, 422)


class USDAProviderTests(unittest.IsolatedAsyncioTestCase):
    def payload(self):
        return {'fdcId': 123, 'description': 'Broccoli, raw', 'dataType': 'Foundation',
            'foodNutrients': [{'nutrient': {'id': nutrient_id, 'unitName': unit}, 'amount': value}
                for nutrient_id, unit, value in [(1008, 'KCAL', 100), (1003, 'G', 10), (1004, 'G', 5),
                                                  (1005, 'G', 15), (1079, 'G', 2), (1093, 'MG', 20)]],
            'foodPortions': [{'amount': 1, 'gramWeight': 90, 'measureUnit': {'name': 'cup'}}]}

    async def test_search_details_parsing_and_units(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.params['api_key'], 'test-key')
            if request.url.path.endswith('search'):
                self.assertEqual(json.loads(request.content)['dataType'], ['Foundation', 'SR Legacy'])
                return httpx.Response(200, json={'foods': [self.payload()]})
            return httpx.Response(200, json=self.payload())
        provider = USDAFoodDataCentralProvider(Settings(usda_api_key='test-key'), httpx.MockTransport(handler))
        result = await provider.lookup(NORMALIZER.normalize('raw broccoli', 100, 'g'))
        self.assertEqual(result.nutrients_per_100g.sodium, 20)
        self.assertEqual(result.nutrient_ids['protein'], 1003)
        self.assertEqual(result.portions[0].gram_weight, 90)
        self.assertEqual(len(calls), 2)

    async def test_ambiguous_wrong_state_and_branded_matches_abstain(self):
        for foods in [[self.payload(), self.payload()], [self.payload() | {'description': 'Broccoli, cooked'}],
                       [self.payload() | {'dataType': 'Branded'}], []]:
            provider = USDAFoodDataCentralProvider(Settings(usda_api_key='test-key'),
                httpx.MockTransport(lambda _: httpx.Response(200, json={'foods': foods})))
            self.assertIsNone(await provider.lookup(NORMALIZER.normalize('raw broccoli', 100, 'g')))

    async def test_identical_cross_dataset_match_prefers_foundation(self):
        foundation = self.payload() | {'dataType': 'Foundation'}
        legacy = self.payload() | {'dataType': 'SR Legacy', 'fdcId': 456}
        def handler(request):
            return httpx.Response(200, json={'foods': [legacy, foundation]} if request.url.path.endswith('search') else foundation)
        provider = USDAFoodDataCentralProvider(Settings(usda_api_key='test-key'), httpx.MockTransport(handler))
        self.assertEqual((await provider.lookup(NORMALIZER.normalize('raw broccoli', 100, 'g'))).data_type, 'Foundation')

    def test_cutting_suffix_preserves_identity_and_state(self):
        ingredient = NORMALIZER.normalize('raw boneless, skinless chicken breast, cut into bite-sized cubes', 350, 'g')
        self.assertEqual(ingredient.name, 'boneless, skinless chicken breast')
        self.assertEqual(ingredient.food_state, 'raw')
        self.assertEqual(ingredient.preparation, 'cut into bite-sized cubes')
        self.assertEqual(ingredient.grams, 350)

    async def test_missing_key_and_http_failures(self):
        with self.assertRaises(NutritionProviderError):
            await USDAFoodDataCentralProvider(Settings()).lookup(NORMALIZER.normalize('raw broccoli', 100, 'g'))
        for status in (401, 403, 429, 500):
            provider = USDAFoodDataCentralProvider(Settings(usda_api_key='test-key'),
                httpx.MockTransport(lambda _: httpx.Response(status, text='private response')))
            with self.assertRaises(NutritionProviderError) as caught:
                await provider.lookup(NORMALIZER.normalize('raw broccoli', 100, 'g'))
            self.assertNotIn('private', str(caught.exception))

    def test_energy_alternatives_not_added_and_absent_values_null(self):
        payload = self.payload()
        payload['foodNutrients'] += [{'nutrient': {'id': 2047, 'unitName': 'KCAL'}, 'amount': 105}]
        result = USDAFoodDataCentralProvider._parse_food(payload, 'raw')
        self.assertEqual(result.nutrients_per_100g.calories, 100)
        payload['foodNutrients'] = [{'nutrient': {'id': 1008, 'unitName': 'kJ'}, 'amount': 100}]
        result = USDAFoodDataCentralProvider._parse_food(payload, 'raw')
        self.assertIsNone(result.nutrients_per_100g.calories)
        self.assertIsNone(result.nutrients_per_100g.protein)

    def test_qualified_portion_does_not_establish_unqualified_volume(self):
        payload = self.payload()
        payload['foodPortions'][0]['portionDescription'] = '1 cup chopped'
        self.assertEqual(USDAFoodDataCentralProvider._parse_food(payload, 'raw').portions, [])
