"""Deterministic product regressions; no network or account mutation."""
import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.core.auth import AuthenticatedUser
from app.core.errors import GenerationError
from app.api.routes.recipes import generation_user, get_recipe_service
from app.services.generation_preferences import generation_context
from app.services.pantry import PantryService
from app.services.normalization import IngredientNormalizationService
from app.services.substitutions import SubstitutionService, substitution_identity
from app.services.recipes import RecipeService
from app.services.nutrition import NutritionService
from app.providers.gemini import GeminiRecipeProvider
from app.providers.usda import match_key
from app.schemas.recipes import RecipeIngredient, RecipeGenerationRequest
from app.schemas.persistence import PreferencesInput
from app.services.generation_preferences import merge_preferences
from tests.test_substitutions import request
from tests.test_recipes import FIXTURE
from tests.test_nutrition import food

def fit(pantry_name, recipe_name, amount=5, unit='piece', required=600, recipe_unit='g', extra=None):
    items = [RecipeIngredient(name=recipe_name,quantity=float(required),unit=recipe_unit)]
    if extra: items.append(items[0])
    return PantryService.compare(items,[dict(id=str(uuid4()),name=pantry_name,quantity=amount,unit=unit)]).ingredients[0]

class ProductPantryTests(unittest.TestCase):
    def test_count_chicken_is_present_without_weight_claim(self):
        for name in ('Chicken Breast','boneless chicken breast','raw chicken breast'):
            result=fit(name,'raw chicken breast')
            self.assertEqual(result.status,'available')
            self.assertEqual(result.quantity_status,'unknown')
    def test_mass_units_sufficient(self):
        self.assertEqual(fit('raw chicken breast','raw chicken breast',1,'kg').quantity_status,'sufficient')
    def test_mass_units_insufficient(self):
        self.assertEqual(fit('raw chicken breast','raw chicken breast',.2,'kg').quantity_status,'insufficient')
    def test_volume_not_mass(self):
        self.assertEqual(fit('olive oil','olive oil',1,'cup').quantity_status,'unknown')
    def test_missing(self):
        self.assertEqual(fit('broccoli','chicken breast').status,'missing')
    def test_parent_child_unknown(self):
        self.assertEqual(fit('chicken','chicken breast').status,'unknown')
    def test_states_and_forms_never_equivalent(self):
        for a,b in [('cooked chicken breast','raw chicken breast'),('dry black beans','canned black beans'),('garlic powder','garlic')]:
            self.assertNotEqual(fit(a,b).status,'available')
    def test_duplicate_rows_do_not_double_spend_stock(self):
        self.assertEqual(fit('salt','salt',600,'g',400,extra=True).quantity_status,'unknown')
    def test_qualifier_does_not_prove_weight(self):
        self.assertEqual(fit('chicken breast','boneless chicken breast',1000,'g').quantity_status,'unknown')

class ProductSubstitutionTests(unittest.TestCase):
    def test_cold_topping_names_plain_yogurt(self):
        body=request('sour cream');body.recipe.title='Cold topping';body.recipe.instructions=['Mix sour cream into the cold topping.']
        option=SubstitutionService().browse(body,body.restrictions)['candidates'][0]
        self.assertEqual(option['name'],'plain yogurt')
        self.assertEqual(option['ratio'],1)
    def test_generated_names_reach_identity_without_erasing_state(self):
        for text,name,state in [('fresh garlic, minced','garlic','raw'),('raw shrimp, peeled and deveined','shrimp','raw'),('canned black beans, rinsed and drained','black bean','canned')]:
            value=substitution_identity(text)
            self.assertEqual(value['normalized_name'],name)
            self.assertEqual(value['food_state'],state)
    def test_ordinary_salad_has_multiple_supported_ingredients(self):
        for name in ['fresh garlic, minced','fresh lime juice','olive oil','canned black beans, rinsed and drained','cooked shrimp']:
            body=request(name,'g'); body.recipe.title='Lunch salad';body.recipe.instructions=['Mix '+name+' into the salad dressing.']
            self.assertTrue(SubstitutionService().browse(body,body.restrictions)['candidates'],name)
    def test_raw_protein_and_salt_are_not_invented_swaps(self):
        for name in ['raw shrimp, peeled and deveined','salt']:
            body=request(name);body.recipe.title='Lunch salad'
            self.assertFalse(SubstitutionService().browse(body,body.restrictions)['candidates'])
    def test_dressing_not_applied_to_heated_or_preserved_recipe(self):
        body=request('olive oil');body.recipe.title='Salad dressing'
        for instruction in ['Heat olive oil in a pan.','Preserve the dressing with olive oil.']:
            body.recipe.instructions=[instruction]
            self.assertFalse(SubstitutionService().browse(body,body.restrictions)['candidates'])
    def test_vegan_shellfish_and_exclusions_filter_ready_proteins(self):
        body=request('cooked chicken breast','g')
        body.restrictions.dietary_preferences=['vegan'];body.restrictions.allergies=['shellfish'];body.restrictions.excluded_ingredients=['kidney beans']
        found=SubstitutionService().browse(body,body.restrictions)
        self.assertTrue(found['candidates'])
        self.assertTrue(all(c['name'] in ('cooked black bean','cooked chickpea') for c in found['candidates']))
    def test_powder_requires_explicit_amount(self):
        body=request('fresh garlic, minced','clove');body.recipe.title='Salad dressing';body.recipe.instructions=['Mix fresh garlic, minced into the dressing.']
        option=SubstitutionService().browse(body,body.restrictions)['candidates'][0]
        self.assertIsNone(option['ratio'])
    def test_saute_oil_requires_explicit_moderate_heat(self):
        body=request('olive oil','tbsp');body.recipe.title='Vegetable skillet'
        body.recipe.instructions=['Heat olive oil over medium heat and saute vegetables.']
        self.assertEqual(SubstitutionService().browse(body,body.restrictions)['candidates'][0]['name'],'canola oil')
        body.recipe.instructions=['Heat olive oil over high heat until smoking.']
        self.assertFalse(SubstitutionService().browse(body,body.restrictions)['candidates'])
    def test_alias_instructions_update_with_canned_variant(self):
        body=request('canned black beans, rinsed and drained','g')
        body.recipe.instructions=['Mix black beans into a bowl.']
        variant=SubstitutionService().variant(body.recipe,0,'kidney bean',100,'g')
        self.assertNotIn('black beans',variant.instructions[0])
        self.assertIn('kidney bean',variant.instructions[0])

class ProductNutritionTests(unittest.IsolatedAsyncioTestCase):
    async def test_generated_names_partial_arithmetic_and_provenance(self):
        normalize=IngredientNormalizationService().normalize
        names=['raw shrimp, peeled and deveined','fresh garlic, minced','fresh lime juice','olive oil','salt','black pepper','canned black beans, rinsed and drained']
        normalized=[normalize(name,100,'g') for name in names]
        self.assertEqual(match_key(normalized[0].name+' '+normalized[0].food_state),match_key('Crustaceans, shrimp, raw'))
        self.assertEqual(normalized[2].food_state,'raw')
        self.assertIn('drained solids',normalized[-1].name)
        provider=AsyncMock();provider.lookup.side_effect=[food()]*5+[None,None]
        result=await NutritionService(provider).calculate(normalized,1)
        self.assertEqual(result.nutrition_status,'partial')
        self.assertEqual(result.calculated_nutrition.known_per_serving.calories,500)
        self.assertIsNone(result.calculated_nutrition.per_serving.calories)
        self.assertEqual(len([s for s in result.nutrition_sources if s.food]),5)

class ProductPreferenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_merge_keeps_request_allergies_and_ranges(self):
        request=RecipeGenerationRequest(selected_ingredients=['broccoli'],allergies=['sesame'],calorie_range={'maximum':500.0})
        result=merge_preferences(request,PreferencesInput(allergies=['peanuts'],nutrition_targets={'calorie_target':600}))
        self.assertEqual(set(result.allergies),{'sesame','peanuts'})
        self.assertEqual(result.calorie_range.maximum,500);self.assertIsNone(result.calorie_target)
    async def test_persisted_defaults_and_request_precedence(self):
        prefs=PreferencesInput(dietary_preferences=['vegetarian','gluten-free','dairy-free'],allergies=['peanuts','custom seed'],excluded_ingredients=['mushrooms'],preferred_cuisines=['Indian'],nutrition_targets={'calorie_target':600,'protein_target':35,'carbs_target':70,'fat_target':20})
        with patch('app.services.generation_preferences.UserPreferencesRepository') as repo:
            repo.return_value.get=AsyncMock(return_value=prefs.model_dump())
            context=await generation_context(RecipeGenerationRequest(selected_ingredients=['broccoli']),object(),Settings())
            self.assertEqual(context.cuisine,'Indian');self.assertEqual(context.calorie_target,600)
            self.assertEqual(context.protein_target,35);self.assertEqual(context.carbs_target,70);self.assertEqual(context.fat_target,20)
            self.assertEqual(set(context.allergies),{'peanuts','custom seed'})
            provider=GeminiRecipeProvider(Settings());provider._request=AsyncMock(return_value='{}')
            await provider.generate(context)
            passed=json.loads(provider._request.call_args.args[1])
            self.assertIn('vegetarian',passed['dietary_preferences']);self.assertIn('mushrooms',passed['excluded_ingredients'])
            again=await generation_context(RecipeGenerationRequest(selected_ingredients=['broccoli'],calorie_target=500,cuisine='Mexican',dietary_preferences=['vegan']),object(),Settings())
            self.assertEqual(again.calorie_target,500);self.assertEqual(again.cuisine,'Mexican')
            self.assertIn('vegetarian',again.dietary_preferences);self.assertIn('vegan',again.dietary_preferences)
    async def test_conflicting_saved_exclusion_rejected(self):
        with patch('app.services.generation_preferences.UserPreferencesRepository') as repo:
            repo.return_value.get=AsyncMock(return_value=PreferencesInput(excluded_ingredients=['mushrooms']).model_dump())
            with self.assertRaises(GenerationError):
                await generation_context(RecipeGenerationRequest(selected_ingredients=['mushrooms']),object(),Settings())
    async def test_account_failure_does_not_generate_without_restrictions(self):
        with patch('app.services.generation_preferences.UserPreferencesRepository') as repo:
            repo.return_value.get=AsyncMock(side_effect=GenerationError('supabase_unavailable','Unavailable',503))
            with self.assertRaises(GenerationError):
                await generation_context(RecipeGenerationRequest(selected_ingredients=['broccoli']),object(),Settings())

class ProductPreferenceEndpointTests(unittest.TestCase):
    def test_route_loads_preferences_and_independently_fails_calorie_goal(self):
        app=create_app(Settings());provider=AsyncMock();provider.name='test';provider.model='test'
        recipe=FIXTURE | dict(ingredients=[dict(name='broccoli',quantity=100.0,unit='g')],servings=1)
        provider.generate.return_value=json.dumps(recipe)
        nutrition_provider=AsyncMock();nutrition_provider.lookup.return_value=food(calories=700)
        app.dependency_overrides[generation_user]=lambda:AuthenticatedUser(id=str(uuid4()),token='test')
        app.dependency_overrides[get_recipe_service]=lambda:RecipeService(provider,nutrition_service=NutritionService(nutrition_provider))
        with patch('app.services.generation_preferences.UserPreferencesRepository') as repo:
            repo.return_value.get=AsyncMock(return_value=PreferencesInput(nutrition_targets={'calorie_target':600},dietary_preferences=['vegetarian'],excluded_ingredients=['mushrooms'],preferred_cuisines=['Indian']).model_dump())
            with TestClient(app) as client:
                for _ in range(2):
                    response=client.post('/api/recipes/generate',json={'selected_ingredients':['broccoli'],'servings':1})
                    self.assertEqual(response.status_code,200,response.text)
                    result=response.json();self.assertEqual(result['evaluated_request']['cuisine'],'Indian')
                    check=next(c for c in result['constraint_results'] if c['constraint']=='maximum_calories')
                    self.assertEqual(check['actual'],700);self.assertEqual(check['status'],'failed')
            self.assertEqual(repo.return_value.get.await_count,2)
