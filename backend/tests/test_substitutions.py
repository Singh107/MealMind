import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.core.auth import AuthenticatedUser
from app.core.errors import GenerationError
from app.api.routes.substitutions import optional_user
from app.schemas.recipes import RecipeCandidate, RecipeGenerationRequest
from app.schemas.substitutions import SubstitutionRequest, SubstitutionPreviewRequest
from app.services.substitutions import SubstitutionService
from app.services.substitution_knowledge import RELATIONSHIPS
from app.services.nutrition import NutritionService
from app.providers.nutrition import NutritionProviderError
from tests.test_recipes import FIXTURE
from tests.test_nutrition import food


def request(name='cooked brown rice',unit='cup',**changes):
    recipe=RecipeCandidate.model_validate(FIXTURE | dict(title='Simple grain bowl',ingredients=[{'name':name,'quantity':1.0,'unit':unit}],
        instructions=['Layer '+name+' into a bowl.'],prep_time=5,cook_time=0,total_time=5))
    restrictions=RecipeGenerationRequest(selected_ingredients=['preference validation'])
    return SubstitutionRequest(recipe=recipe,ingredient_index=0,restrictions=restrictions,**changes)

def preview_payload(body,**kwargs):
    option=SubstitutionService().browse(body,body.restrictions)['candidates'][0]
    return SubstitutionPreviewRequest(**body.model_dump(),relationship_id=option['relationship_id'],**kwargs)

class SubstitutionTests(unittest.TestCase):
    def test_catalog_relationships_no_self_edges(self):
        self.assertEqual(len(RELATIONSHIPS),140)
        self.assertEqual(len({x.id for x in RELATIONSHIPS}),140)
        self.assertTrue(all(x.source!=x.target for x in RELATIONSHIPS))

    def test_known_lookup_and_ratio(self):
        body=request();result=SubstitutionService().browse(body,body.restrictions)
        self.assertEqual(len(result['candidates']),4)
        self.assertTrue(all(x['ratio']==1 for x in result['candidates']))

    def test_normalization_plural_reused(self):
        body=request('cooked carrots');result=SubstitutionService().browse(body,body.restrictions)
        self.assertEqual(len(result['candidates']),3)

    def test_unsupported_and_raw_unresolved(self):
        for name in ['raw brown rice','special mix','brown rice','raw cooked brown rice']:
            body=request(name)
            self.assertEqual(SubstitutionService().browse(body,body.restrictions)['candidates'],[])

    def test_role_context_title_and_cooking_filter(self):
        for title,step in [('Rice pudding','Layer cooked brown rice.'),('Grain bowl','Boil cooked brown rice.'),('Grain bowl','Serve lunch.')]:
            body=request();body.recipe.title=title;body.recipe.instructions=[step]
            self.assertEqual(SubstitutionService().browse(body,body.restrictions)['candidates'],[])

    def test_unknown_ratio_for_mass(self):
        body=request(unit='g')
        self.assertTrue(all(x['ratio'] is None for x in SubstitutionService().browse(body,body.restrictions)['candidates']))

    def test_known_dietary_conflict_blocks_all(self):
        body=request();body.recipe.ingredients.append(type(body.recipe.ingredients[0])(name='milk',quantity=1.0,unit='cup'))
        body.restrictions.dietary_preferences=['vegan']
        result=SubstitutionService().browse(body,body.restrictions)
        self.assertEqual(result['blocked_count'],4);self.assertEqual(result['candidates'],[])

    def test_allergy_and_exclusion_conflicts(self):
        for field in ['allergies','excluded_ingredients']:
            body=request();setattr(body.restrictions,field,['quinoa'])
            names=[x['name'] for x in SubstitutionService().browse(body,body.restrictions)['candidates']]
            self.assertNotIn('cooked quinoa',names)

    def test_uncertain_safety_not_certified(self):
        body=request();body.restrictions.allergies=['milk']
        result=SubstitutionService().browse(body,body.restrictions)
        self.assertTrue(all(x['compatibility']=='uncertain' for x in result['candidates']))

    def test_pantry_and_deterministic_order(self):
        body=request();pantry=[{'id':'11111111-1111-4111-8111-111111111111','name':'cooked white rice'}]
        service=SubstitutionService();first=service.browse(body,body.restrictions,pantry,'loaded')
        self.assertEqual(first,service.browse(body,body.restrictions,pantry,'loaded'))
        self.assertEqual(first['candidates'][0]['name'],'cooked white rice')
        self.assertEqual(first['candidates'][0]['availability'],'available')

    def test_duplicate_candidate_not_proposed(self):
        body=request();body.recipe.ingredients.append(type(body.recipe.ingredients[0])(name='raw quinoa',quantity=1.0,unit='g'))
        candidates=SubstitutionService().browse(body,body.restrictions)['candidates']
        self.assertEqual(len(candidates),3)
        self.assertNotIn('cooked quinoa',[x['name'] for x in candidates])

    def test_browse_no_nutrition_or_gemini_calls(self):
        nutrition=AsyncMock();body=request()
        SubstitutionService(nutrition).browse(body,body.restrictions)
        nutrition.calculate.assert_not_called()

    def test_signed_out_route_and_bad_index(self):
        client=TestClient(create_app(Settings()))
        body=request().model_dump(mode='json')
        self.assertEqual(client.post('/api/ingredients/substitutions',json=body).status_code,200)
        body['ingredient_index']=3
        self.assertEqual(client.post('/api/ingredients/substitutions',json=body).status_code,422)
        body['ingredient_index']=0;body['user_id']='spoof'
        self.assertEqual(client.post('/api/ingredients/substitutions',json=body).status_code,422)

    def test_authenticated_restrictions_override_client_and_pantry_failure(self):
        app=create_app(Settings());app.dependency_overrides[optional_user]=lambda:AuthenticatedUser('user-a','token')
        prefs={'dietary_preferences':[],'allergies':[],'excluded_ingredients':['quinoa','white rice','couscous','pasta'],
            'nutrition_targets':{},'preferred_cuisines':[],'cooking_preferences':{}}
        with patch('app.api.routes.substitutions.UserPreferencesRepository') as repo,patch('app.api.routes.substitutions.PantryRepository') as pantry:
            repo.return_value.get=AsyncMock(return_value=prefs)
            pantry.return_value.list=AsyncMock(side_effect=GenerationError('unavailable','Unavailable',503))
            result=TestClient(app).post('/api/ingredients/substitutions',json=request().model_dump(mode='json')).json()
            self.assertEqual(result['candidates'],[]);self.assertEqual(result['pantry_state'],'unavailable')
            self.assertEqual(repo.call_args.args[1].id,'user-a')

class PreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_one_original_retained_and_recalculated(self):
        body=request(unit='g');payload=preview_payload(body,quantity=200.0,unit='g');original=copy.deepcopy(body.recipe.model_dump())
        provider=AsyncMock();provider.lookup=AsyncMock(return_value=food())
        result=await SubstitutionService(NutritionService(provider)).preview(payload,body.restrictions)
        self.assertEqual(body.recipe.model_dump(),original)
        self.assertEqual(result['change']['before']['name'],'cooked brown rice')
        self.assertEqual(result['change']['after']['quantity'],200)
        self.assertNotEqual(result['original_recipe']['recipe_version_id'],result['final_recipe']['recipe_version_id'])
        self.assertEqual(provider.lookup.await_count,2)
        self.assertIsNone(result['final_recipe']['nutrition']['calories'])
        self.assertNotIn('cooked brown rice',result['final_recipe']['instructions'][0])
        self.assertEqual(result['after_intelligence']['calculated_nutrition']['per_serving']['calories'],200/body.recipe.servings)

    async def test_unknown_ratio_requires_input(self):
        body=request(unit='g')
        with self.assertRaises(GenerationError) as error:
            await SubstitutionService(AsyncMock()).preview(preview_payload(body),body.restrictions)
        self.assertEqual(error.exception.code,'substitution_quantity_required')

    async def test_known_ratio_defaults_without_mass_assumption(self):
        body=request();provider=AsyncMock();provider.lookup=AsyncMock(return_value=None)
        result=await SubstitutionService(NutritionService(provider)).preview(preview_payload(body),body.restrictions)
        self.assertEqual(result['change']['after']['unit'],'cup')
        self.assertEqual(result['change']['after']['quantity'],1)
        self.assertIsNone(result['after_intelligence']['calculated_nutrition']['per_serving']['calories'])

    async def test_partial_and_constraint_recheck_ignores_ai(self):
        body=request(unit='g');body.restrictions.protein_target=35
        provider=AsyncMock();provider.lookup=AsyncMock(return_value=food(protein=None))
        result=await SubstitutionService(NutritionService(provider)).preview(preview_payload(body,quantity=540.0,unit='g'),body.restrictions)
        self.assertEqual(result['after_intelligence']['constraint_results'][0]['status'],'unknown')
        self.assertIsNone(result['after_intelligence']['calculated_nutrition']['per_serving']['protein'])
        self.assertEqual(result['after_intelligence']['nutrition_status'],'partial')

    async def test_provider_unavailable_leaves_unknown(self):
        body=request(unit='g');provider=AsyncMock();provider.lookup=AsyncMock(side_effect=NutritionProviderError('unavailable'))
        result=await SubstitutionService(NutritionService(provider)).preview(preview_payload(body,quantity=2.0,unit='g'),body.restrictions)
        self.assertEqual(result['after_intelligence']['nutrition_status'],'unavailable')

    async def test_timeout_sanitized(self):
        body=request()
        async def wait(*args,**kwargs):await asyncio.sleep(1)
        nutrition=AsyncMock();nutrition.calculate.side_effect=wait
        with self.assertRaises(GenerationError) as error:
            await SubstitutionService(nutrition,timeout=.001).preview(preview_payload(body),body.restrictions)
        self.assertEqual(error.exception.code,'substitution_timeout')

    async def test_unknown_hard_safety_preview_cannot_be_used(self):
        body=request();body.restrictions.allergies=['milk'];provider=AsyncMock();provider.lookup=AsyncMock(return_value=None)
        result=await SubstitutionService(NutritionService(provider)).preview(preview_payload(body),body.restrictions)
        self.assertFalse(result['can_use'])

    async def test_apply_revalidates_tampered_relationship(self):
        body=request();payload=SubstitutionPreviewRequest(**body.model_dump(),relationship_id='invented')
        with self.assertRaises(GenerationError):await SubstitutionService(AsyncMock()).preview(payload,body.restrictions)
