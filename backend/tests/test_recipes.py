import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.api.routes.recipes import get_recipe_service
from app.core.config import Settings
from app.core.errors import GenerationError
from app.main import create_app
from app.providers.gemini import GeminiRecipeProvider
from app.schemas.recipes import GeneratedRecipe, RecipeCandidate, RecipeGenerationRequest
from app.services.recipes import RecipeService

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/recipe-v1.json').read_text())


class SchemaTests(unittest.TestCase):
    def test_valid_request_and_serialization(self):
        request = RecipeGenerationRequest(selected_ingredients=[' Lentils '], calorie_target=0,
                                          dietary_preferences=['vegan', 'gluten-free'],
                                          allergies=['peanuts', 'shellfish'], excluded_ingredients=['mushrooms'])
        data = json.loads(request.model_dump_json())
        self.assertEqual(data['selected_ingredients'], ['Lentils'])
        self.assertEqual(data['calorie_target'], 0)
        self.assertEqual(data['dietary_preferences'], ['vegan', 'gluten-free'])
        self.assertEqual(data['allergies'], ['peanuts', 'shellfish'])
        self.assertEqual(data['excluded_ingredients'], ['mushrooms'])
        self.assertIsNone(data['protein_target'])

    def test_invalid_requests(self):
        for changes in [dict(selected_ingredients=[]), dict(selected_ingredients=[' ']),
                        dict(selected_ingredients=['x' * 121]), dict(servings=0), dict(servings=1.5),
                        dict(servings=True), dict(servings='4'), dict(protein_target=-1),
                        dict(calorie_target=float('nan')), dict(fat_target=101),
                        dict(dietary_preferences=['made-up']), dict(allergies='nuts'),
                        dict(spice_level='extreme'), dict(max_cooking_time=0), dict(unknown=True),
                        dict(excluded_ingredients=['lentils']), dict(allergies=['Lentils'])]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                RecipeGenerationRequest(**({'selected_ingredients': ['Lentils']} | changes))

    def test_structured_recipe_and_unknown_nutrition(self):
        recipe = GeneratedRecipe(**FIXTURE, id=uuid4(), recipe_version_id=uuid4())
        self.assertEqual(recipe.validation_status, 'unverified')
        self.assertIsNone(recipe.nutrition.sodium)
        self.assertEqual(recipe.nutrition_basis, 'per_serving')
        self.assertEqual(GeneratedRecipe.model_validate_json(recipe.model_dump_json()), recipe)

    def test_malformed_recipes(self):
        for changes in [dict(instructions=[]), dict(instructions='markdown'), dict(total_time=99),
                        dict(ingredients=[{'name': 'Tofu', 'quantity': 0, 'unit': 'g'}]),
                        dict(nutrition={'calories': -1, 'protein': 0, 'carbohydrates': 0, 'fat': 0}),
                        dict(title=''), dict(rating=4.8), dict(validation_status='validated')]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                RecipeCandidate.model_validate(FIXTURE | changes)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings())
        self.provider = AsyncMock()
        self.provider.name = 'test-provider'
        self.provider.model = 'fixture-v1'
        self.provider.generate.return_value = json.dumps(FIXTURE)
        self.service = RecipeService(self.provider)
        self.app.dependency_overrides[get_recipe_service] = lambda: self.service
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_health_and_existing_endpoints(self):
        self.assertEqual(self.client.get('/health').json()['status'], 'ok')
        self.assertTrue(self.client.get('/api/test').json()['data']['test'])
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_success_calls_provider_and_validates_response(self):
        response = self.client.post('/api/recipes/generate', json={'selected_ingredients': ['Lentils'],
                                    'dietary_preferences': ['vegan'], 'allergies': ['nuts']})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        recipe = GeneratedRecipe.model_validate_json(json.dumps(data['recipe']))
        self.assertEqual(recipe.title, FIXTURE['title'])
        self.assertEqual(recipe.validation_status, 'unverified')
        UUID(data['trace_id'])
        self.assertEqual(data['trace_id'], response.headers['x-trace-id'])
        sent = self.provider.generate.call_args.args[0]
        self.assertEqual(sent.dietary_preferences, ['vegan'])
        self.assertEqual(sent.allergies, ['nuts'])
        self.provider.generate.assert_awaited_once()
        self.assertEqual(data['metadata']['schema_version'], '1.1')

    def test_endpoint_through_real_adapter_with_mock_http_transport(self):
        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body['generationConfig']['responseMimeType'], 'application/json')
            return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP',
                'content': {'parts': [{'text': json.dumps(FIXTURE)}]}}]})
        self.service = RecipeService(GeminiRecipeProvider(Settings(gemini_api_key='test-key'),
                                                         httpx.MockTransport(handler)))
        response = self.client.post('/api/recipes/generate', json={'selected_ingredients': ['Lentils']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['metadata']['provider'], 'gemini')
        self.assertEqual(response.json()['recipe']['title'], FIXTURE['title'])

    def test_invalid_input_does_not_call_provider(self):
        response = self.client.post('/api/recipes/generate', json={'selected_ingredients': [], 'servings': -1})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'invalid_request')
        self.assertTrue(response.json()['error']['field_issues'])
        self.provider.generate.assert_not_awaited()

    def test_invalid_json_body(self):
        response = self.client.post('/api/recipes/generate', content='{bad', headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('{bad', response.text)

    def test_invalid_ai_output(self):
        for raw in ['```json\n{}\n```', '{broken', '{}', json.dumps(FIXTURE | {'servings': 2})]:
            with self.subTest(raw=raw):
                self.provider.generate.return_value = raw
                response = self.client.post('/api/recipes/generate', json={'selected_ingredients': ['Lentils']})
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json()['error']['code'], 'invalid_provider_output')

    def test_provider_errors(self):
        for status, code in [(503, 'provider_not_configured'), (504, 'provider_timeout'),
                             (429, 'provider_rate_limited'), (502, 'provider_failure')]:
            with self.subTest(status=status):
                self.provider.generate.side_effect = GenerationError(code, 'Please retry.', status)
                response = self.client.post('/api/recipes/generate', json={'selected_ingredients': ['Lentils']},
                                            headers={'Origin': 'http://127.0.0.1:3001'})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()['error']['code'], code)
                self.assertEqual(response.headers['access-control-allow-origin'], 'http://127.0.0.1:3001')

    def test_missing_key_real_adapter(self):
        self.service = RecipeService(GeminiRecipeProvider(Settings(gemini_api_key='')))
        response = self.client.post('/api/recipes/generate', json={'selected_ingredients': ['Lentils']})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['error']['retryable'])

    def test_deadline(self):
        async def slow(_):
            await asyncio.sleep(1)
        self.provider.generate.side_effect = slow
        self.service.timeout_seconds = .01
        response = self.client.post('/api/recipes/generate', json={'selected_ingredients': ['Lentils']})
        self.assertEqual(response.status_code, 504)

    def test_unexpected_error_is_redacted(self):
        self.provider.generate.side_effect = RuntimeError('secret-provider-payload')
        response = self.client.post('/api/recipes/generate', json={'selected_ingredients': ['Lentils']},
                                    headers={'Origin': 'http://127.0.0.1:3001'})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('secret-provider-payload', response.text)
        self.assertEqual(response.headers['access-control-allow-origin'], 'http://127.0.0.1:3001')
        self.assertEqual(response.headers['x-trace-id'], response.json()['error']['trace_id'])

    def test_cors_preflight(self):
        headers = {'Origin': 'http://127.0.0.1:3001', 'Access-Control-Request-Method': 'POST',
                   'Access-Control-Request-Headers': 'content-type'}
        self.assertEqual(self.client.options('/api/recipes/generate', headers=headers).status_code, 200)
        headers['Origin'] = 'https://untrusted.example'
        self.assertNotIn('access-control-allow-origin', self.client.options('/api/recipes/generate', headers=headers).headers)


class GeminiTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_retry_succeeds_and_is_bounded(self):
        for recover in [True, False]:
            calls = []
            def handler(request):
                calls.append(request)
                if recover and len(calls) == 2:
                    return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(FIXTURE)}]}}]})
                return httpx.Response(503, json={'error': {'status': 'UNAVAILABLE'}})
            provider = GeminiRecipeProvider(Settings(gemini_api_key='test-key'), httpx.MockTransport(handler))
            if recover:
                self.assertEqual(json.loads(await provider.generate(RecipeGenerationRequest(selected_ingredients=['Lentils']))), FIXTURE)
            else:
                with self.assertRaises(GenerationError):
                    await provider.generate(RecipeGenerationRequest(selected_ingredients=['Lentils']))
            self.assertEqual(len(calls), 2)

    async def test_nontransient_errors_are_not_retried(self):
        for status, code in [(400, 'INVALID_ARGUMENT'), (403, 'PERMISSION_DENIED'), (404, 'NOT_FOUND'), (429, 'RESOURCE_EXHAUSTED')]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status, json={'error': {'status': code}})
            provider = GeminiRecipeProvider(Settings(gemini_api_key='test-key'), httpx.MockTransport(handler))
            with self.assertRaises(GenerationError):
                await provider.generate(RecipeGenerationRequest(selected_ingredients=['Lentils']))
            self.assertEqual(len(calls), 1)

    async def test_retry_backoff_respects_service_deadline(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(503, json={'error': {'status': 'UNAVAILABLE'}})
        service = RecipeService(GeminiRecipeProvider(Settings(gemini_api_key='test-key'), httpx.MockTransport(handler)), timeout_seconds=.01)
        with self.assertRaises(GenerationError) as caught:
            await service.generate(RecipeGenerationRequest(selected_ingredients=['Lentils']), 'deadline-test')
        self.assertEqual(caught.exception.code, 'provider_timeout')
        self.assertEqual(len(calls), 1)

    async def test_safe_upstream_diagnostics_exclude_payload_and_unknown_codes(self):
        for upstream, expected in [('UNAVAILABLE', 'UNAVAILABLE'), ('private-test-key', 'UNKNOWN')]:
            provider = GeminiRecipeProvider(Settings(gemini_api_key='test-key'), httpx.MockTransport(
                lambda request: httpx.Response(503, json={'error': {'status': upstream, 'message': 'private-test-key'}})))
            with self.assertLogs('app.providers.gemini', level='WARNING') as logs:
                with self.assertRaises(GenerationError) as caught:
                    await provider.generate(RecipeGenerationRequest(selected_ingredients=['Lentils']))
            self.assertTrue(caught.exception.retryable)
            self.assertIn('upstream_status=' + expected, logs.output[0])
            self.assertNotIn('private-test-key', ' '.join(logs.output))

    async def test_wire_contract(self):
        def handler(request):
            self.assertNotIn('test-key', str(request.url))
            self.assertEqual(request.headers['x-goog-api-key'], 'test-key')
            body = json.loads(request.content)
            config = body['generationConfig']
            self.assertNotIn('candidateCount', config)
            self.assertEqual(config['responseMimeType'], 'application/json')
            self.assertIn(json.dumps(RecipeCandidate.model_json_schema()), body['systemInstruction']['parts'][0]['text'])
            sent = json.loads(body['contents'][0]['parts'][0]['text'])
            self.assertEqual(sent['allergies'], ['nuts'])
            return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(FIXTURE)}]}}]})
        provider = GeminiRecipeProvider(Settings(gemini_api_key='test-key'), httpx.MockTransport(handler))
        raw = await provider.generate(RecipeGenerationRequest(selected_ingredients=['Lentils'], allergies=['nuts']))
        self.assertEqual(RecipeCandidate.model_validate_json(raw).title, FIXTURE['title'])

    async def test_http_failures_and_bad_envelopes(self):
        cases = [(401, {}, 'provider_authentication_failed'), (403, {}, 'provider_authentication_failed'),
                 (429, {}, 'provider_rate_limited'), (500, {}, 'provider_failure'),
                 (200, {}, 'no_recipe_generated'), (200, [], 'invalid_provider_output'),
                 (200, {'candidates': [{'finishReason': 'MAX_TOKENS'}]}, 'incomplete_provider_output'),
                 (200, {'candidates': [{'finishReason': 'STOP', 'content': {'parts': []}}]}, 'invalid_provider_output')]
        for status, body, code in cases:
            with self.subTest(code=code):
                provider = GeminiRecipeProvider(Settings(gemini_api_key='test-key'),
                    httpx.MockTransport(lambda _: httpx.Response(status, json=body)))
                with self.assertRaises(GenerationError) as caught:
                    await provider.generate(RecipeGenerationRequest(selected_ingredients=['Lentils']))
                self.assertEqual(caught.exception.code, code)

    async def test_transport_timeout_and_network_failure(self):
        for exception, code in [(httpx.ReadTimeout('secret'), 'provider_timeout'),
                                (httpx.ConnectError('secret'), 'provider_unavailable')]:
            def handler(_):
                raise exception
            provider = GeminiRecipeProvider(Settings(gemini_api_key='test-key'), httpx.MockTransport(handler))
            with self.assertRaises(GenerationError) as caught:
                await provider.generate(RecipeGenerationRequest(selected_ingredients=['Lentils']))
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn('secret', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
