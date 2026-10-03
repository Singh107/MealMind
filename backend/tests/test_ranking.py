import copy
import json
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.schemas.persistence import PreferencesInput
from app.schemas.recipes import GeneratedRecipe
from app.services.ranking import RankingService

BASE = json.loads((Path(__file__).parent / 'fixtures/recipe-v1.json').read_text())

def row(key='a', names=('salt',), **changes):
    recipe = GeneratedRecipe(**(BASE | {'ingredients': [{'name': n, 'quantity': 1.0, 'unit': 'g'} for n in names]} | changes), id=uuid4(), recipe_version_id=uuid4())
    return {'id': key, 'recipe': {'structuredRecipe': recipe.model_dump(mode='json')}}

class RankingTests(unittest.TestCase):
    def rank(self, rows, names=('salt',), **prefs):
        return RankingService().rank(rows, [{'id': '11111111-1111-4111-8111-111111111111', 'name': n} for n in names], PreferencesInput(**prefs))

    def test_deterministic_and_stable_ties(self):
        a, b = row('a'), row('b')
        self.assertEqual(self.rank([a,b]), self.rank([b,a]))
        self.assertEqual([x['saved_recipe_id'] for x in self.rank([b,a])['entries']], ['a','b'])

    def test_pantry_component_and_missing_penalty(self):
        result = self.rank([row('missing', ('salt','broccoli')), row('have')])
        self.assertEqual(result['entries'][0]['saved_recipe_id'], 'have')
        self.assertEqual(result['entries'][0]['components']['pantry_fit'], 60)
        self.assertEqual(result['entries'][1]['components']['missing_penalty'], -2)

    def test_unknown_never_available(self):
        e = self.rank([row(names=('salt','special blend'))])['entries'][0]
        self.assertEqual(e['pantry']['available_count'], 1)
        self.assertEqual(e['eligibility'], 'uncertain')
        self.assertEqual(e['components']['unknown_penalty'], -2.5)

    def test_allergy_conflict_excluded(self):
        r = self.rank([row(names=('milk',))], names=('milk',), allergies=['milk'])
        self.assertEqual(r['state'], 'all_ineligible'); self.assertEqual(r['entries'], [])

    def test_exclusion_conflict(self):
        self.assertEqual(self.rank([row()], excluded_ingredients=['salt'])['ineligible_count'], 1)

    def test_vegan_conflict(self):
        self.assertEqual(self.rank([row(names=('chicken breast',))], dietary_preferences=['vegan'])['ineligible_count'], 1)

    def test_unknown_allergy_is_not_pass(self):
        r = self.rank([row()], allergies=['milk'])
        self.assertEqual(r['state'], 'only_uncertain')
        self.assertEqual(r['entries'][0]['constraints'][0]['status'], 'unknown')

    def test_soft_cuisine_and_difficulty(self):
        e = self.rank([row(cuisine='Italian',difficulty='beginner')], preferred_cuisines=['italian'], cooking_preferences={'difficulty':'beginner'})['entries'][0]
        self.assertEqual(e['components']['preferences'], 10)
        self.assertTrue(any(x['code']=='preference_match' for x in e['reasons']))

    def test_no_targets_no_pass_bonus(self):
        self.assertEqual(self.rank([row()])['entries'][0]['components']['constraints'], 0)

    def test_saved_nutrition_pass_fail_unknown_and_current_targets(self):
        a = row(); snapshot = a['recipe']['structuredRecipe']
        recipe = GeneratedRecipe.model_validate_json(json.dumps({k:v for k,v in snapshot.items() if k in GeneratedRecipe.model_fields}))
        report = RankingService.evidence(recipe, {})
        report.nutrition_status = 'partial'
        report.calculated_nutrition.coverage['calories'] = 1
        report.calculated_nutrition.per_serving.calories = 540
        snapshot['intelligence'] = report.model_dump(mode='json')
        for target, status in [(600,'passed'), (490,'failed')]:
            e = self.rank([a], nutrition_targets={'calorie_target':target})['entries'][0]
            self.assertEqual(e['constraints'][0]['status'],status)
            self.assertEqual(e['constraints'][0]['actual'],540)
            self.assertIn('saved nutrition',e['reasons'][-1]['text'])
        snapshot['intelligence']['calculated_nutrition']['coverage']['calories']=0
        e = self.rank([a], nutrition_targets={'calorie_target':600})['entries'][0]
        self.assertEqual(e['constraints'][0]['status'],'unknown')

    def test_ai_estimate_not_used(self):
        e=self.rank([row()],nutrition_targets={'calorie_target':2000})['entries'][0]
        self.assertIsNone(e['constraints'][0]['actual'])
        self.assertEqual(e['eligibility'],'uncertain')

    def test_eligibility_before_score(self):
        r=self.rank([row('uncertain',('salt','special blend')),row('eligible',('broccoli',))])
        self.assertEqual(r['entries'][0]['saved_recipe_id'],'eligible')

    def test_empty_and_invalid_sources(self):
        self.assertEqual(self.rank([])['state'],'no_candidates')
        self.assertEqual(self.rank([{'recipe':{}},{'recipe':{'structuredRecipe':{'title':'fake'}}}])['skipped_count'],2)
        self.assertEqual(self.rank([row()],names=())['state'],'empty_pantry')
        self.assertEqual(self.rank([row()],names=('special blend',))['entries'],[])

    def test_limits_and_input_not_mutated(self):
        rows=[row('b'),row('a')]; before=copy.deepcopy(rows)
        r=RankingService().rank(rows,[{'id':'11111111-1111-4111-8111-111111111111','name':'salt'}],PreferencesInput(),limit=1,offset=1)
        self.assertEqual(r['total'],2);self.assertEqual(r['entries'][0]['rank'],2)
        self.assertEqual(rows,before)

    def test_explanation_matches_counts(self):
        e=self.rank([row(names=('salt','broccoli','special blend'))])['entries'][0]
        self.assertIn('1 of 3',e['reasons'][0]['text'])
        self.assertIn('broccoli',e['reasons'][1]['text'])
        self.assertIn('special blend',e['reasons'][2]['text'])

    def test_endpoint_auth_isolation_and_no_provider_calls(self):
        saved = row()
        original = httpx.AsyncClient
        calls=[]
        def transport(request):
            calls.append(request.url.path)
            owner='11111111-1111-4111-8111-111111111111' if request.headers.get('authorization')=='Bearer a' else '22222222-2222-4222-8222-222222222222'
            if request.url.path=='/auth/v1/user':return httpx.Response(200,json={'id':owner})
            self.assertEqual(request.url.params['user_id'],'eq.'+owner)
            self.assertEqual(request.headers['apikey'],'public')
            if request.url.path=='/rest/v1/saved_recipes':return httpx.Response(200,json=[saved] if owner.startswith('1') else [])
            if request.url.path=='/rest/v1/pantry_items':return httpx.Response(200,json=[{'id':'11111111-1111-4111-8111-111111111111','name':'salt'}])
            if request.url.path=='/rest/v1/user_preferences':return httpx.Response(200,json=[])
            self.fail('Unexpected provider/network request')
        with patch('httpx.AsyncClient',side_effect=lambda **kw: original(transport=httpx.MockTransport(transport),**kw)):
            client=TestClient(create_app(Settings(supabase_url='https://test.supabase.co',supabase_anon_key='public')))
            self.assertEqual(client.get('/api/recommendations/pantry').status_code,401)
            self.assertEqual(client.get('/api/recommendations/pantry',headers={'Authorization':'Bearer a'}).json()['total'],1)
            self.assertEqual(client.get('/api/recommendations/pantry',headers={'Authorization':'Bearer b'}).json()['total'],0)
            for query in ['limit=0','limit=51','offset=-1','offset=10001']:
                self.assertEqual(client.get('/api/recommendations/pantry?'+query,headers={'Authorization':'Bearer a'}).status_code,422)
        self.assertTrue(all(x.startswith('/rest/v1/') or x=='/auth/v1/user' for x in calls))
