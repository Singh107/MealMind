import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.core.errors import GenerationError
from app.api.routes.meal import get_meal_vision, get_meal_nutrition
from app.providers.meal_vision import GeminiMealVisionProvider
from app.providers.nutrition import NutritionProviderError
from app.services.meal import MealVisionService, MealNutritionService
from app.services.nutrition import NutritionService
from app.schemas.meal import MealNutritionRequest
from tests.test_vision import picture, detection, FixtureVision
from tests.test_nutrition import food


def request(names=('broccoli',), unit='g', quantity=200.):
    return MealNutritionRequest(confirmed=True, components=[dict(name=n,quantity=quantity,unit=unit) for n in names])


def vision(items=None):
    p=FixtureVision()
    p.analyze.return_value=json.dumps({'meal_name':'Meal', 'components':items if items is not None else [detection('broccoli'),detection('cheese pizza','low')]})
    return p


class MealVisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_multi_composite_uncertainty_normalization(self):
        result=await MealVisionService(vision()).analyze(picture(),'image/png')
        self.assertEqual(len(result.components),2)
        self.assertEqual(result.components[0].canonical_name,'broccoli')
        self.assertEqual(result.components[1].display_name,'cheese pizza')
        self.assertEqual(result.components[1].confidence,'low')
        self.assertEqual(result.components[1].identity_status,'unresolved')
        self.assertNotIn('quantity',result.model_dump()['components'][0])

    async def test_empty(self):
        self.assertEqual((await MealVisionService(vision([])).analyze(picture(),'image/png')).components,[])

    async def test_images_reuse_cleaning(self):
        for fmt,mime in [('JPEG','image/jpeg'),('PNG','image/png'),('WEBP','image/webp')]:
            provider=vision()
            with patch('app.services.meal.prepare_image', wraps=__import__('app.services.vision',fromlist=['prepare_image']).prepare_image) as clean:
                await MealVisionService(provider).analyze(picture(fmt),mime)
            clean.assert_called_once(); self.assertEqual(provider.analyze.call_args.args[1],'image/jpeg')

    async def test_invalid_image_no_provider(self):
        p=vision()
        with self.assertRaises(GenerationError): await MealVisionService(p).analyze(b'invalid','image/png')
        p.analyze.assert_not_called()

    async def test_schema_and_ai_nutrients_rejected(self):
        for raw in ['{', json.dumps({'components':[], 'calories':400}), json.dumps({'components':[dict(detection(),quantity=100)]}), json.dumps({'components':[detection(confidence='0.99')]})]:
            p=vision();p.analyze.return_value=raw
            with self.assertRaises(GenerationError) as e: await MealVisionService(p).analyze(picture(),'image/png')
            self.assertEqual(e.exception.code,'vision_invalid_output')

    async def test_conflicting_state(self):
        result=await MealVisionService(vision([detection('raw broccoli',state='cooked')])).analyze(picture(),'image/png')
        self.assertEqual(result.components[0].identity_status,'conflicting')

    async def test_timeout(self):
        p=vision()
        async def slow(*a): await asyncio.sleep(5)
        p.analyze.side_effect=slow
        with self.assertRaises(GenerationError) as e: await MealVisionService(p,.01).analyze(picture(),'image/png')
        self.assertEqual(e.exception.code,'vision_timeout')

    async def test_no_nutrition_or_persistence(self):
        with patch('app.services.nutrition.NutritionService.calculate',side_effect=AssertionError()), patch('app.services.pantry.PantryService.save',side_effect=AssertionError()):
            await MealVisionService(vision()).analyze(picture(),'image/png')

    async def test_meal_provider_reuses_transport_and_own_schema(self):
        def handler(r):
            payload=json.loads(r.content)
            self.assertIn('MealVisionProposal',payload['systemInstruction']['parts'][0]['text'])
            self.assertIn('hidden',payload['systemInstruction']['parts'][0]['text'])
            return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"components":[]}'}]}}]})
        p=GeminiMealVisionProvider(Settings(gemini_api_key='test'),httpx.MockTransport(handler))
        self.assertEqual(await p.analyze(b'image','image/jpeg'),'{"components":[]}')


class MealNutritionTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_scaling_and_no_gemini(self):
        provider=AsyncMock();provider.lookup.return_value=food(sugar=3)
        with patch('app.providers.vision.GeminiVisionProvider.analyze',side_effect=AssertionError()), patch('app.services.pantry.PantryService.save',side_effect=AssertionError()):
            result=await MealNutritionService(NutritionService(provider)).calculate(request())
        self.assertEqual(result.nutrition.nutrition_status,'verified')
        self.assertEqual(result.nutrition.calculated_nutrition.totals.calories,200)
        self.assertEqual(result.nutrition.calculated_nutrition.totals.sugar,6)
        self.assertEqual(result.nutrition.calculated_nutrition.servings,1)
        self.assertEqual(provider.lookup.call_args.args[0].grams,200)

    async def test_partial_preserves_missing(self):
        p=AsyncMock();p.lookup.side_effect=[food(),None]
        result=await MealNutritionService(NutritionService(p)).calculate(request(('broccoli','mystery meal')))
        self.assertEqual(result.nutrition.nutrition_status,'partial')
        self.assertIsNone(result.nutrition.calculated_nutrition.totals.calories)
        self.assertEqual(result.nutrition.calculated_nutrition.known_totals.calories,200)
        self.assertEqual(result.nutrition.nutrition_sources[1].status,'unmatched')

    async def test_unavailable_provider(self):
        p=AsyncMock();p.lookup.side_effect=NutritionProviderError('PRIVATE')
        result=await MealNutritionService(NutritionService(p)).calculate(request())
        self.assertEqual(result.nutrition.nutrition_status,'unavailable')
        self.assertNotIn('PRIVATE',result.model_dump_json())

    async def test_portion_without_evidence_not_guessed(self):
        p=AsyncMock();p.lookup.return_value=food()
        result=await MealNutritionService(NutritionService(p)).calculate(request(unit='cup',quantity=1.))
        self.assertEqual(result.nutrition.nutrition_sources[0].status,'unconvertible')
        self.assertIsNone(result.nutrition.calculated_nutrition.totals.calories)

    def test_bad_quantities(self):
        for q in (0.,-1.,float('inf'),True,'100'):
            with self.subTest(q=q),self.assertRaises(ValidationError): request(quantity=q)

    def test_supported_units_only(self):
        with self.assertRaises(ValidationError): request(unit='serving')
        self.assertEqual(request(unit='grams').components[0].unit,'g')

    def test_confirmation_and_no_extra_fields(self):
        for extra in ({'confirmed':False},{'user_id':'fake'},{'nutrition':{'calories':1}}):
            data=request().model_dump();data.update(extra)
            with self.assertRaises(ValidationError): MealNutritionRequest.model_validate(data)


class MealRouteTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app(Settings());self.p=vision()
        self.app.dependency_overrides[get_meal_vision]=lambda:MealVisionService(self.p)
        provider=AsyncMock();provider.lookup.return_value=food()
        self.app.dependency_overrides[get_meal_nutrition]=lambda:MealNutritionService(NutritionService(provider))
        self.client=TestClient(self.app)

    def test_anonymous_vision(self):
        r=self.client.post('/api/vision/meal',content=picture(),headers={'Content-Type':'image/png'})
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['components']),2)

    def test_anonymous_nutrition(self):
        r=self.client.post('/api/nutrition/meal',json=request().model_dump())
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['nutrition']['calculated_nutrition']['totals']['calories'],200)

    def test_no_owner_input(self):
        self.assertEqual(self.client.post('/api/vision/meal?user_id=a',content=picture(),headers={'Content-Type':'image/png'}).status_code,422)
        self.assertEqual(self.client.post('/api/nutrition/meal',json={**request().model_dump(),'user_id':'a'}).status_code,422)

    def test_vision_provider_failure(self):
        self.p.analyze.side_effect=GenerationError('vision_unavailable','Temporarily unavailable',503)
        r=self.client.post('/api/vision/meal',content=picture(),headers={'Content-Type':'image/png'})
        self.assertEqual(r.status_code,503)

    def test_sanitized_unexpected_failure(self):
        self.p.analyze.side_effect=RuntimeError('PRIVATE')
        r=self.client.post('/api/vision/meal',content=picture(),headers={'Content-Type':'image/png'})
        self.assertEqual(r.status_code,500);self.assertNotIn('PRIVATE',r.text)
