import asyncio
import unittest
from unittest.mock import AsyncMock
import httpx
from app.core.config import Settings
from app.providers.usda import USDAFoodDataCentralProvider
from app.providers.usda import match_key
from app.schemas.intelligence import FoodPortion
from app.services.nutrition import NutritionService
from tests.test_nutrition import food, NORMALIZER


class CoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_connection_pool_lifecycle(self):
        provider = USDAFoodDataCentralProvider(Settings(usda_api_key='test-key'),
            httpx.MockTransport(lambda request: httpx.Response(200, json={'foods': []})))
        async with provider:
            client = provider.client
            await asyncio.gather(provider.lookup(NORMALIZER.normalize('raw broccoli', 100, 'g')),
                                 provider.lookup(NORMALIZER.normalize('raw carrots', 100, 'g')))
            self.assertIs(provider.client, client)
            self.assertFalse(client.is_closed)
        self.assertTrue(client.is_closed)
        self.assertIsNone(provider.client)

    def test_identity_synonyms_preserve_nutritional_qualifiers(self):
        for left, right in [('broccoli florets raw', 'Broccoli, flower clusters, raw'),
                            ('garlic clove raw', 'Garlic, raw'),
                            ('red bell pepper raw', 'Peppers, sweet, red, raw'),
                            ('ground black pepper', 'Spices, pepper, black'),
                            ('dry white long-grain rice unenriched', 'Rice, white, long-grain, regular, raw, unenriched')]:
            self.assertEqual(match_key(left), match_key(right))
        for left, right in [('chicken breast raw', 'chicken soup raw'),
                            ('chicken breast skinless raw', 'chicken breast meat and skin raw'),
                            ('broccoli florets raw', 'broccoli stalks raw'),
                            ('rice raw', 'rice cooked'), ('rice unenriched raw', 'rice enriched raw'),
                            ('garlic raw', 'garlic bread raw')]:
            self.assertNotEqual(match_key(left), match_key(right))

    def test_preparation_adverbs_and_equivalent_states(self):
        for prep in ['finely chopped', 'roughly diced', 'thinly sliced', 'coarsely minced']:
            item = NORMALIZER.normalize('raw garlic, ' + prep, 10, 'g')
            self.assertEqual(item.name, 'garlic')
            self.assertEqual(item.grams, 10)
        self.assertEqual(NORMALIZER.normalize('raw uncooked rice', 100, 'g').food_state, 'raw')
        self.assertEqual(NORMALIZER.normalize('raw cooked rice', 100, 'g').status, 'unresolved')

    async def test_volume_ratios_use_matched_record_mass(self):
        record = food()
        record.portions = [FoodPortion(unit='tbsp', amount=1, gram_weight=13.5, description='tablespoon'),
                           FoodPortion(unit='cup', amount=1, gram_weight=216, description='cup')]
        provider = AsyncMock(); provider.lookup.return_value = record
        for amount, unit, expected in [(30, 'ml', 27), (.1, 'l', 90), (2, 'tsp', 9), (2, 'tbsp', 27), (.5, 'cup', 108)]:
            result = await NutritionService(provider).calculate([NORMALIZER.normalize('olive oil', amount, unit)], 1)
            self.assertAlmostEqual(result.nutrition_sources[0].ingredient.grams, expected)
        record.portions[1].gram_weight = 200
        result = await NutritionService(provider).calculate([NORMALIZER.normalize('olive oil', 30, 'ml')], 1)
        self.assertEqual(result.nutrition_sources[0].status, 'unconvertible')

    async def test_bounded_concurrency_completes_later_ingredients(self):
        active = peak = calls = 0
        gate = asyncio.Event()
        async def lookup(ingredient):
            nonlocal active, peak, calls
            active += 1; calls += 1; peak = max(peak, active)
            if active == 4:
                gate.set()
            await gate.wait()
            await asyncio.sleep(0)
            active -= 1
            return food()
        provider = AsyncMock(); provider.lookup.side_effect = lookup
        ingredients = [NORMALIZER.normalize(f'ingredient {i}', 100, 'g') for i in range(8)]
        result = await NutritionService(provider, 1).calculate(ingredients + [ingredients[0]], 1)
        self.assertEqual(peak, 4)
        self.assertEqual(calls, 8)
        self.assertEqual(result.nutrition_status, 'verified')
        self.assertEqual(result.calculated_nutrition.coverage['calories'], 9)

    async def test_parent_cancellation_cleans_up_lookups(self):
        started = asyncio.Event()
        active = 0
        async def lookup(ingredient):
            nonlocal active
            active += 1; started.set()
            try:
                await asyncio.Event().wait()
            finally:
                active -= 1
        provider = AsyncMock(); provider.lookup.side_effect = lookup
        task = asyncio.create_task(NutritionService(provider).calculate([NORMALIZER.normalize(str(i), 100, 'g') for i in range(8)], 1))
        await started.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(active, 0)
