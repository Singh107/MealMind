import json
import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.services.pantry import pantry_identity

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'


class PantryTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.calls = []
        self.failure = None
        original = httpx.AsyncClient

        def transport(request):
            self.calls.append(request)
            token = request.headers.get('authorization')
            owner = A if token == 'Bearer a' else B if token == 'Bearer b' else None
            if request.url.path == '/auth/v1/user':
                return httpx.Response(200, json={'id': owner}) if owner else httpx.Response(401)
            self.assertEqual(request.url.path, '/rest/v1/pantry_items')
            self.assertEqual(request.headers['apikey'], 'public')
            self.assertEqual(request.url.params['user_id'], 'eq.' + owner)
            if self.failure:
                return httpx.Response(self.failure, json={'message': 'PRIVATE UPSTREAM DETAIL'})
            # Independent simulated database RLS, in addition to owner filters.
            rows = [r for r in self.rows if r['user_id'] == owner]
            for field in ('id', 'identity_key'):
                if field in request.url.params:
                    rows = [r for r in rows if request.url.params[field] == 'eq.' + r[field]]
            body = json.loads(request.content) if request.content else None
            if request.method == 'POST':
                self.assertEqual(body['user_id'], owner)
                if any(r['identity_key'] == body['identity_key'] and r['user_id'] == owner for r in self.rows):
                    return httpx.Response(409)
                row = {**body, 'id': str(uuid4()), 'created_at': '2026-09-16T00:00:00Z', 'updated_at': '2026-09-16T00:00:00Z'}
                self.rows.append(row)
                return httpx.Response(201, json=[row])
            if request.method == 'PATCH':
                self.assertNotIn('user_id', body)
                for row in rows:
                    row.update(body)
            if request.method == 'DELETE':
                self.rows = [r for r in self.rows if r not in rows]
            if request.method == 'GET':
                start = int(request.url.params.get('offset', 0))
                rows = rows[start:start + int(request.url.params.get('limit', 10000))]
            return httpx.Response(200, json=rows)

        self.patcher = patch('httpx.AsyncClient', side_effect=lambda **kw: original(transport=httpx.MockTransport(transport), **kw))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = TestClient(create_app(Settings(supabase_url='https://test.supabase.co', supabase_anon_key='public', supabase_service_role_key='NEVER-USED')))
        self.headers = {'Authorization': 'Bearer a'}

    def create(self, name='Chicken Breasts', **values):
        return self.client.post('/api/pantry', headers=self.headers, json={'name': name, **values})

    def coverage(self, *names, headers=None):
        return self.client.post('/api/pantry/compatibility', headers=headers or self.headers,
            json={'ingredients': [{'name': n, 'quantity': 1, 'unit': 'g'} for n in names]})

    def test_crud_and_normalized_persistence(self):
        created = self.create(quantity=2, unit='pounds')
        self.assertEqual(created.status_code, 201)
        row = created.json()
        self.assertEqual(row['name'], 'Chicken Breasts')
        self.assertEqual(row['normalized_name'], 'chicken breast')
        self.assertEqual(row['unit'], 'lb')
        self.assertEqual(self.rows[0]['user_id'], A)
        self.assertNotIn('user_id', row)
        self.assertNotIn('identity_key', row)
        path = '/api/pantry/' + row['id']
        self.assertEqual(self.client.get(path, headers=self.headers).json(), row)
        response = self.client.put(path, headers=self.headers, json={'name': 'Raw broccoli', 'quantity': 3, 'unit': 'kg'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['food_state'], 'raw')
        self.assertEqual(response.json()['normalized_name'], 'broccoli')
        self.assertEqual(self.client.get('/api/pantry', headers=self.headers).json(), [response.json()])
        self.assertEqual(self.client.delete(path, headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get(path, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get('/api/pantry', headers=self.headers).json(), [])

    def test_auth_required_on_all_operations(self):
        path = '/api/pantry/' + str(uuid4())
        for method, url, body in [('GET', '/api/pantry', None), ('POST', '/api/pantry', {'name': 'salt'}),
                                 ('PUT', path, {'name': 'salt'}), ('DELETE', path, None), ('GET', path, None),
                                 ('POST', '/api/pantry/compatibility', {'ingredients': []})]:
            self.assertEqual(self.client.request(method, url, json=body).status_code, 401)
        self.assertFalse(self.calls)

    def test_invalid_token(self):
        self.assertEqual(self.client.get('/api/pantry', headers={'Authorization': 'Bearer bad'}).status_code, 401)

    def test_cross_user_isolation_all_operations(self):
        row = self.create().json()
        b = {'Authorization': 'Bearer b'}
        self.assertEqual(self.client.get('/api/pantry', headers=b).json(), [])
        path = '/api/pantry/' + row['id']
        for method in ('GET', 'PUT', 'DELETE'):
            response = self.client.request(method, path, headers=b, json={'name': 'salt'} if method == 'PUT' else None)
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(path, headers=self.headers).json(), row)
        self.assertEqual(self.coverage('chicken breast', headers=b).json()['pantry_count'], 0)

    def test_client_cannot_set_owner_or_normalized_fields(self):
        for field, value in [('user_id', B), ('normalized_name', 'salt'), ('identity_key', 'a'*64), ('identity_status', 'recognized')]:
            self.assertEqual(self.create(**{field: value}).status_code, 422)
        self.assertEqual(self.rows, [])

    def test_quantity_and_name_validation(self):
        for body in [{'name': ''}, {'name': '   '}, {'name': 'x'*121}, {'name': 'salt', 'quantity': 0},
                     {'name': 'salt', 'quantity': -1}, {'name': 'salt', 'quantity': True},
                     {'name': 'salt', 'quantity': 100001}, {'name': 'salt', 'unit': 'bucket'}]:
            self.assertEqual(self.client.post('/api/pantry', headers=self.headers, json=body).status_code, 422)

    def test_unknown_quantity_and_unit_allowed(self):
        row = self.create('special blend').json()
        self.assertIsNone(row['quantity'])
        self.assertIsNone(row['unit'])
        self.assertEqual(row['identity_status'], 'unresolved')

    def test_duplicate_plural_rejected_without_arithmetic(self):
        self.create(quantity=2, unit='lb')
        response = self.create('chicken breast', quantity=1, unit='kg')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error']['code'], 'pantry_duplicate')
        self.assertEqual(len(self.rows), 1)
        self.assertEqual(self.rows[0]['quantity'], 2)

    def test_update_cannot_duplicate_other_item(self):
        self.create('salt')
        row = self.create('broccoli').json()
        response = self.client.put('/api/pantry/' + row['id'], headers=self.headers, json={'name': 'salt'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.rows), 2)

    def test_same_identity_in_separate_accounts_allowed(self):
        self.create()
        self.assertEqual(self.client.post('/api/pantry', headers={'Authorization': 'Bearer b'}, json={'name': 'chicken breast'}).status_code, 201)

    def test_food_states_and_qualifiers_not_merged(self):
        for name in ['raw chicken breast', 'cooked chicken breast', 'boneless chicken breast', 'chicken breast']:
            self.assertEqual(self.create(name).status_code, 201)
        self.assertEqual(len(self.rows), 4)
        self.assertEqual(pantry_identity('boneless chicken breast')['identity_status'], 'unresolved')

    def test_composition_alias_is_not_a_substitution(self):
        self.create('peanut butter')
        result = self.coverage('peanuts').json()
        self.assertEqual(result['available_count'], 0)
        self.assertNotEqual(pantry_identity('ground beef')['identity_key'], pantry_identity('beef')['identity_key'])

    def test_compatibility_available_missing_unknown(self):
        self.create('chicken breasts')
        self.create('special blend')
        result = self.coverage('chicken breast', 'broccoli', 'special blend', 'boneless chicken breast').json()
        self.assertEqual([r['status'] for r in result['ingredients']], ['available', 'missing', 'unknown', 'available'])
        self.assertEqual(result['coverage_percent'], 50)
        self.assertEqual(result['unknown_count'], 1)

    def test_state_conflict_and_unspecified_state_are_unknown(self):
        self.create('raw broccoli')
        result = self.coverage('broccoli', 'cooked broccoli', 'raw cooked broccoli', 'raw broccoli').json()
        self.assertEqual([r['status'] for r in result['ingredients']], ['unknown', 'unknown', 'unknown', 'available'])

    def test_quantity_does_not_claim_sufficiency(self):
        self.create('salt', quantity=.01, unit='g')
        result = self.coverage('salt').json()
        self.assertEqual(result['available_count'], 1)
        self.assertEqual(result['ingredients'][0]['quantity_status'], 'insufficient')

    def test_qualified_pantry_name_is_unknown_not_definitely_missing(self):
        self.create('boneless chicken breast')
        result = self.coverage('chicken breast').json()
        self.assertEqual(result['ingredients'][0]['status'], 'available')
        self.assertEqual(result['ingredients'][0]['quantity_status'], 'unknown')
        self.assertEqual(result['usable_pantry_count'], 1)
        self.assertEqual(result['coverage_percent'], 100)

    def test_unknowns_remain_in_coverage_denominator(self):
        self.create('salt')
        result = self.coverage('salt', 'special blend').json()
        self.assertEqual(result['coverage_percent'], 50)
        self.assertEqual(result['ingredient_count'], 2)
        self.assertEqual(result['usable_pantry_count'], 1)

    def test_empty_pantry_has_no_percentage(self):
        self.assertIsNone(self.coverage('salt').json()['coverage_percent'])

    def test_stored_metadata_is_not_matching_authority(self):
        self.create('special blend')
        self.rows[0].update(pantry_identity('salt'))
        self.assertEqual(self.coverage('salt').json()['available_count'], 0)

    def test_names_outside_catalog_preserved(self):
        for name in ['豆腐', '味噌']:
            self.assertEqual(self.create(name).status_code, 201)
        self.assertNotEqual(self.rows[0]['identity_key'], self.rows[1]['identity_key'])

    def test_provider_errors_sanitized(self):
        for status, expected in [(401, 401), (403, 403), (409, 409), (500, 503)]:
            self.failure = status
            result = self.client.get('/api/pantry', headers=self.headers)
            self.assertEqual(result.status_code, expected)
            self.assertNotIn('PRIVATE', result.text)
            self.assertNotIn('NEVER-USED', result.text)

    def test_pagination(self):
        self.create('salt')
        row = self.rows[0]
        self.rows = [{**row, 'id': str(uuid4())} for _ in range(501)]
        self.assertEqual(len(self.client.get('/api/pantry', headers=self.headers).json()), 501)

    def test_no_usda_or_gemini_called(self):
        self.create('salt')
        self.coverage('salt')
        self.assertTrue(all(r.url.path in ('/auth/v1/user', '/rest/v1/pantry_items') for r in self.calls))


if __name__ == '__main__': unittest.main()
