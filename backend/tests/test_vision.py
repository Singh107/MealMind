import asyncio
import json
from io import BytesIO
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.core.errors import GenerationError
from app.api.routes.vision import get_vision_service
from app.providers.vision import GeminiVisionProvider
from app.services.vision import IngredientVisionService, prepare_image, MAX_IMAGE_BYTES


def picture(fmt='PNG'):
    out = BytesIO()
    Image.new('RGB', (20, 20), 'green').save(out, fmt)
    return out.getvalue()


def detection(name='broccoli', confidence='high', state=None):
    return dict(display_name=name, confidence=confidence, visible_state=state, uncertainty='Review this suggestion.')


class FixtureVision:
    name, model = 'test-fixture', 'test-only'

    def __init__(self, detections=None):
        self.analyze = AsyncMock(return_value=json.dumps({'detections': detections if detections is not None else [detection()]}))


class VisionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_multiple_and_qualitative_confidence(self):
        provider = FixtureVision([detection(), detection('carrot', 'medium'), detection('special blend', 'low')])
        result = await IngredientVisionService(provider).analyze(picture(), 'image/png')
        self.assertEqual([d.confidence for d in result.detections], ['high','medium','low'])
        self.assertEqual(result.detections[0].canonical_name, 'broccoli')
        self.assertEqual(result.detections[2].identity_status, 'unresolved')
        provider.analyze.assert_awaited_once()

    async def test_conflicting_state(self):
        result = await IngredientVisionService(FixtureVision([detection('raw broccoli', state='cooked')])).analyze(picture(), 'image/png')
        self.assertEqual(result.detections[0].identity_status, 'conflicting')

    async def test_duplicate_conservative_identity_and_lowest_confidence(self):
        provider = FixtureVision([detection('tomato'), detection('tomatoes', 'low'), detection('tomato', state='cooked'), detection('unknown mix'), detection('unknown mix')])
        result = await IngredientVisionService(provider).analyze(picture(), 'image/png')
        self.assertEqual(len(result.detections), 4)
        self.assertEqual(result.detections[0].merged_count, 2)
        self.assertEqual(result.detections[0].confidence, 'low')

    async def test_empty_detection_is_valid(self):
        result = await IngredientVisionService(FixtureVision([])).analyze(picture(), 'image/png')
        self.assertEqual(result.detections, [])

    async def test_malformed_and_schema_invalid_output(self):
        for raw in ['{', '{"detections": ["broccoli"]}', json.dumps({'detections': [detection(confidence='93.7%')]}), json.dumps({'detections': [], 'nutrition': 10})]:
            with self.subTest(raw=raw):
                provider = FixtureVision(); provider.analyze.return_value = raw
                with self.assertRaises(GenerationError) as caught:
                    await IngredientVisionService(provider).analyze(picture(), 'image/png')
                self.assertEqual(caught.exception.code, 'vision_invalid_output')

    async def test_timeout_cancels_provider(self):
        provider = FixtureVision()
        cancelled = asyncio.Event()
        async def slow(*args):
            try: await asyncio.sleep(5)
            finally: cancelled.set()
        provider.analyze.side_effect = slow
        with self.assertRaises(GenerationError) as caught:
            await IngredientVisionService(provider, .01).analyze(picture(), 'image/png')
        self.assertEqual(caught.exception.code, 'vision_timeout')
        self.assertTrue(cancelled.is_set())

    async def test_parent_cancellation_propagates(self):
        provider = FixtureVision(); started = asyncio.Event()
        async def slow(*args):
            started.set(); await asyncio.sleep(10)
        provider.analyze.side_effect = slow
        task = asyncio.create_task(IngredientVisionService(provider).analyze(picture(), 'image/png'))
        await started.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task

    async def test_no_nutrition_or_pantry_side_effect(self):
        with patch('app.services.nutrition.NutritionService.calculate', side_effect=AssertionError('No USDA')), \
             patch('app.services.pantry.PantryService.save', side_effect=AssertionError('No write')):
            result = await IngredientVisionService(FixtureVision()).analyze(picture(), 'image/png')
        self.assertEqual(result.detections[0].normalized_name, 'broccoli')


class ImageTests(unittest.TestCase):
    def test_valid_jpeg(self): self.assertTrue(prepare_image(picture('JPEG'), 'image/jpeg').startswith(b'\xff\xd8'))
    def test_valid_png(self): self.assertTrue(prepare_image(picture(), 'image/png').startswith(b'\xff\xd8'))
    def test_valid_webp(self): self.assertTrue(prepare_image(picture('WEBP'), 'image/webp').startswith(b'\xff\xd8'))

    def test_exif_removed_and_orientation_applied(self):
        out = BytesIO(); exif = Image.Exif(); exif[270] = 'PRIVATE metadata'; exif[274] = 6
        Image.new('RGB', (10, 20)).save(out, 'JPEG', exif=exif)
        result = prepare_image(out.getvalue(), 'image/jpeg')
        with Image.open(BytesIO(result)) as image:
            self.assertFalse(image.getexif()); self.assertEqual(image.size, (20, 10))
        self.assertNotIn(b'PRIVATE', result)

    def test_invalid_image(self):
        for content, mime in [(b'corrupt', 'image/png'), (picture(), 'image/jpeg'), (picture('GIF'), 'image/gif')]:
            with self.subTest(mime=mime), self.assertRaises(GenerationError): prepare_image(content, mime)

    def test_empty_image(self):
        with self.assertRaises(GenerationError) as caught: prepare_image(b'', 'image/png')
        self.assertEqual(caught.exception.code, 'vision_empty_image')

    def test_size_bound(self):
        with self.assertRaises(GenerationError) as caught: prepare_image(b'x' * (MAX_IMAGE_BYTES + 1), 'image/png')
        self.assertEqual(caught.exception.status, 413)

    def test_pixel_bound(self):
        with patch('app.services.vision.MAX_PIXELS', 10), self.assertRaises(GenerationError): prepare_image(picture(), 'image/png')

    def test_animation_rejected(self):
        out = BytesIO()
        Image.new('RGB',(10,10),'red').save(out, 'PNG', save_all=True, append_images=[Image.new('RGB',(10,10),'blue')], duration=100)
        with self.assertRaises(GenerationError): prepare_image(out.getvalue(), 'image/png')


class VisionRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings()); self.provider = FixtureVision()
        self.app.dependency_overrides[get_vision_service] = lambda: IngredientVisionService(self.provider)
        self.client = TestClient(self.app)

    def test_anonymous_binary_upload(self):
        response = self.client.post('/api/vision/ingredients', content=picture(), headers={'Content-Type': 'image/png'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['detections'][0]['identity_status'], 'recognized')

    def test_no_owner_input(self):
        response = self.client.post('/api/vision/ingredients?user_id=spoof', content=picture(), headers={'Content-Type': 'image/png'})
        self.assertEqual(response.status_code, 422); self.provider.analyze.assert_not_called()

    def test_bad_mime_and_json_not_upload(self):
        for mime in ('text/plain','application/json','image/gif'):
            response = self.client.post('/api/vision/ingredients', content=b'{}', headers={'Content-Type': mime})
            self.assertEqual(response.status_code, 415)
        self.provider.analyze.assert_not_called()

    def test_stream_size_limit(self):
        response = self.client.post('/api/vision/ingredients', content=b'x' * (MAX_IMAGE_BYTES+1), headers={'Content-Type': 'image/png'})
        self.assertEqual(response.status_code, 413); self.provider.analyze.assert_not_called()

    def test_sanitized_unexpected_error(self):
        self.provider.analyze.side_effect = RuntimeError('PRIVATE_SENTINEL')
        response = self.client.post('/api/vision/ingredients', content=picture(), headers={'Content-Type': 'image/png'})
        self.assertEqual(response.status_code, 500); self.assertNotIn('PRIVATE_SENTINEL', response.text)


class VisionProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_image_request_and_no_retry(self):
        calls = []
        def handler(request):
            calls.append(request)
            data = json.loads(request.content)
            self.assertEqual(data['contents'][0]['parts'][0]['inlineData']['mimeType'], 'image/jpeg')
            self.assertEqual(request.headers['x-goog-api-key'], 'test-only')
            return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts':[{'text':'{"detections": []}'}]}}]})
        provider = GeminiVisionProvider(Settings(gemini_api_key='test-only'), httpx.MockTransport(handler))
        self.assertEqual(await provider.analyze(picture('JPEG'), 'image/jpeg'), '{"detections": []}')
        self.assertEqual(len(calls), 1)

    async def test_sanitized_http_errors(self):
        for status, code in [(429,'vision_rate_limited'),(503,'vision_provider_error'),(403,'vision_provider_error'),(404,'vision_provider_error')]:
            calls=[]
            def handler(request):
                calls.append(1); return httpx.Response(status, text='PRIVATE_SENTINEL')
            provider = GeminiVisionProvider(Settings(gemini_api_key='test-only'), httpx.MockTransport(handler))
            with self.assertRaises(GenerationError) as caught: await provider.analyze(b'test', 'image/jpeg')
            self.assertEqual(caught.exception.code, code); self.assertNotIn('PRIVATE_SENTINEL', str(caught.exception)); self.assertEqual(len(calls),1)

    async def test_network_timeout_and_unavailable(self):
        for error, code in [(httpx.ReadTimeout('private'), 'vision_timeout'),(httpx.ConnectError('private'), 'vision_unavailable')]:
            def handler(request): raise error
            with self.assertRaises(GenerationError) as caught:
                await GeminiVisionProvider(Settings(gemini_api_key='test-only'), httpx.MockTransport(handler)).analyze(b'test','image/jpeg')
            self.assertEqual(caught.exception.code, code)

    async def test_invalid_envelope(self):
        provider = GeminiVisionProvider(Settings(gemini_api_key='test-only'), httpx.MockTransport(lambda r: httpx.Response(200,json={'candidates':[]})))
        with self.assertRaises(GenerationError) as caught: await provider.analyze(b'test','image/jpeg')
        self.assertEqual(caught.exception.code,'vision_invalid_output')
