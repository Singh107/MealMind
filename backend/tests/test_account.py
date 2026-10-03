import json
from pathlib import Path
from copy import deepcopy
import unittest
from unittest.mock import patch
from uuid import UUID
import httpx
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.schemas.persistence import PreferencesInput

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
RID = '33333333-3333-4333-8333-333333333333'
SNAPSHOT = {'id': 'legacy-1', 'name': 'Meal', 'ingredients': ['broccoli'], 'instructions': 'Cook',
    'prepTime': '1 min', 'cookTime': '2 min', 'difficulty': 'beginner', 'servings': 2,
    'nutrition': {'calories': None, 'protein': None, 'carbs': None, 'fat': None}, 'savedAt': '2026-09-14',
    'structuredRecipe': {'intelligence': {'known_per_serving': {'calories': 250}, 'status': 'partial'},
        'optimization': {'original_recipe': {'title': 'Original'}, 'repair_status': 'partially_repaired'}}}

class AccountTests(unittest.TestCase):
    def setUp(self):
        self.rows = {}
        self.single = {}
        self.calls = []
        self.failure = None
        original_client = httpx.AsyncClient
        def transport(request):
            self.calls.append(request)
            token = request.headers.get('authorization', '')
            user = A if token == 'Bearer valid-a' else B if token == 'Bearer valid-b' else None
            if request.url.path == '/auth/v1/user':
                if token == 'Bearer outage': return httpx.Response(503)
                return httpx.Response(200, json={'id': user}) if user else httpx.Response(401, json={})
            if self.failure: return httpx.Response(self.failure, json={})
            # Simulates RLS independently of repository owner filters.
            if not user: return httpx.Response(401)
            self.assertEqual(request.headers['apikey'], 'public-test-key')
            self.assertEqual(request.url.params['user_id'], 'eq.' + user)
            table = request.url.path.rsplit('/', 1)[-1]
            body = json.loads(request.content) if request.content else None
            if table == 'saved_recipes':
                if request.method == 'POST':
                    key = (user, body['source_id'])
                    if key in self.rows: return httpx.Response(200, json=[])
                    row = {**body, 'id': RID, 'created_at': '2026-09-14'}
                    self.rows[key] = row
                    return httpx.Response(201, json=[row])
                rows = [r for (owner, _), r in self.rows.items() if owner == user]
                for field in ['id', 'source_id']:
                    if field in request.url.params:
                        rows = [r for r in rows if 'eq.' + r[field] == request.url.params[field]]
                if request.method == 'DELETE':
                    for r in rows: del self.rows[(user, r['source_id'])]
                return httpx.Response(200, json=rows)
            if request.method == 'POST': self.single[(table, user)] = body
            row = self.single.get((table, user))
            return httpx.Response(200, json=[row] if row else [])
        self.patcher = patch('httpx.AsyncClient', side_effect=lambda **kw: original_client(transport=httpx.MockTransport(transport), **kw))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = TestClient(create_app(Settings(supabase_url='https://test.supabase.co', supabase_anon_key='public-test-key', supabase_service_role_key='NEVER-USED')))
        self.headers = {'Authorization': 'Bearer valid-a'}

    def save(self):
        return self.client.post('/api/saved-recipes', headers=self.headers, json={'source_id': 'legacy-1', 'recipe': SNAPSHOT})

    def test_missing_auth(self):
        self.assertEqual(self.client.get('/api/saved-recipes').status_code, 401)
        self.assertFalse(self.calls)

    def test_invalid_token(self):
        self.assertEqual(self.client.get('/api/saved-recipes', headers={'Authorization': 'Bearer invalid'}).status_code, 401)

    def test_expired_token(self):
        response = self.client.get('/api/preferences', headers={'Authorization': 'Bearer expired'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error']['code'], 'auth_expired')

    def test_valid_user_empty_list(self):
        self.assertEqual(self.client.get('/api/saved-recipes', headers=self.headers).json(), [])

    def test_create_preserves_entire_snapshot(self):
        response = self.save()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['recipe'], SNAPSHOT)
        self.assertEqual(response.json()['user_id'], A)

    def test_complete_captured_intelligence_and_repair_snapshot_roundtrip(self):
        captured = json.loads((Path(__file__).parent / 'fixtures' / 'nutrition-polish-live.json').read_text(encoding='utf-8'))['response']
        recipe = deepcopy(captured['recipe'])
        intelligence = {key: deepcopy(captured[key]) for key in (
            'calculated_nutrition', 'nutrition_status', 'nutrition_sources', 'constraint_results',
            'overall_constraint_status', 'normalized_ingredients') if key in captured}
        recipe['intelligence'] = intelligence
        # Persistence must retain nested repair data unchanged; this is a storage-only fixture.
        recipe['optimization'] = {'repair_status': 'failed', 'repair_attempts': 1,
            'original_recipe': deepcopy(captured['recipe']), 'final_recipe': deepcopy(captured['recipe']),
            'before_intelligence': deepcopy(intelligence), 'after_intelligence': deepcopy(intelligence),
            'changes': [], 'failure_code': 'provider_unavailable'}
        snapshot = {**SNAPSHOT, 'structuredRecipe': recipe, 'generation_metadata': captured['metadata']}
        response = self.client.post('/api/saved-recipes', headers=self.headers,
            json={'source_id': str(recipe['recipe_version_id']), 'recipe': snapshot})
        self.assertEqual(response.status_code, 200)
        loaded = self.client.get('/api/saved-recipes/' + RID, headers=self.headers).json()['recipe']
        self.assertEqual(loaded, snapshot)
        self.assertEqual(loaded['structuredRecipe']['intelligence']['nutrition_status'], 'partial')
        self.assertIsNone(loaded['structuredRecipe']['intelligence']['calculated_nutrition']['per_serving']['calories'])
        self.assertGreater(loaded['structuredRecipe']['intelligence']['calculated_nutrition']['known_per_serving']['calories'], 0)

    def test_list_own(self):
        self.save()
        self.assertEqual(len(self.client.get('/api/saved-recipes', headers=self.headers).json()), 1)
        self.assertEqual(self.client.get('/api/saved-recipes', headers={'Authorization': 'Bearer valid-b'}).json(), [])

    def test_get_own(self):
        self.save()
        self.assertEqual(self.client.get('/api/saved-recipes/' + RID, headers=self.headers).json()['recipe'], SNAPSHOT)

    def test_delete_own(self):
        self.save()
        self.assertEqual(self.client.delete('/api/saved-recipes/' + RID, headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get('/api/saved-recipes/' + RID, headers=self.headers).status_code, 404)

    def test_cannot_get_or_delete_other_user(self):
        self.save()
        for method in ['get', 'delete']:
            self.assertEqual(getattr(self.client, method)('/api/saved-recipes/' + RID, headers={'Authorization': 'Bearer valid-b'}).status_code, 404)
        self.assertEqual(self.client.get('/api/saved-recipes/' + RID, headers=self.headers).status_code, 200)

    def test_frontend_cannot_choose_owner(self):
        response = self.client.post('/api/saved-recipes', headers=self.headers, json={'source_id': 'legacy-1', 'recipe': SNAPSHOT, 'user_id': B})
        self.assertEqual(response.status_code, 422)

    def test_duplicate_import_idempotent(self):
        self.save()
        self.assertEqual(self.save().json()['id'], RID)
        self.assertEqual(len(self.rows), 1)

    def test_preferences_read_write_isolated(self):
        values = PreferencesInput(dietary_preferences=['vegan'], allergies=['nuts'], excluded_ingredients=['rice'],
            nutrition_targets={'calorie_target': 0, 'protein_target': 35}, preferred_cuisines=['Italian'], cooking_preferences={'servings': 2}).model_dump()
        self.assertEqual(self.client.put('/api/preferences', headers=self.headers, json=values).json(), values)
        self.assertEqual(self.client.get('/api/preferences', headers=self.headers).json(), values)
        self.assertEqual(self.client.get('/api/preferences', headers={'Authorization': 'Bearer valid-b'}).json()['allergies'], [])

    def test_invalid_preference_semantics(self):
        response = self.client.put('/api/preferences', headers=self.headers, json={'nutrition_targets': {'protein_target': 900}})
        self.assertEqual(response.status_code, 422)

    def test_profile_read_write(self):
        self.assertEqual(self.client.get('/api/profile', headers=self.headers).json(), {'display_name': ''})
        self.client.put('/api/profile', headers=self.headers, json={'display_name': 'Agam'})
        self.assertEqual(self.client.get('/api/profile', headers=self.headers).json(), {'display_name': 'Agam'})

    def test_auth_service_outage(self):
        response = self.client.get('/api/preferences', headers={'Authorization': 'Bearer outage'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'supabase_unavailable')

    def test_repository_errors_are_sanitized(self):
        for status, code in [(401, 'auth_expired'), (403, 'permission_denied'), (503, 'supabase_unavailable')]:
            self.failure = status
            response = self.client.get('/api/saved-recipes', headers=self.headers)
            self.assertEqual(response.json()['error']['code'], code)
            self.assertNotIn('NEVER-USED', response.text)

    def test_cors_authorization_methods(self):
        response = self.client.options('/api/preferences', headers={'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'PUT', 'Access-Control-Request-Headers': 'authorization,content-type'})
        self.assertEqual(response.status_code, 200)

    def test_unconfigured_does_not_break_public_health(self):
        client = TestClient(create_app(Settings()))
        self.assertEqual(client.get('/health').status_code, 200)
        self.assertEqual(client.get('/api/preferences', headers=self.headers).json()['error']['code'], 'auth_not_configured')

if __name__ == '__main__': unittest.main()
