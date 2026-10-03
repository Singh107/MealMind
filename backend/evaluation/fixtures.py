"""Deliberately synthetic nutrition arithmetic, NEVER actual USDA/Gemini quality."""
import json
from app.core.errors import GenerationError
from app.providers.dev_fixture import DevelopmentRecipeProvider
from app.providers.nutrition import NutritionProviderError
from app.schemas.intelligence import FoodRecord, NutrientValues


class EvaluationRecipeProvider:
    name, model = 'evaluation-fixture', 'synthetic-v1'

    def __init__(self, case):
        self.case = case

    async def generate(self, request):
        scenario = self.case.fixture
        if scenario == 'provider':
            raise GenerationError('provider_unavailable', 'Synthetic outage', 503)
        if scenario == 'timeout':
            raise TimeoutError()
        if scenario == 'parse':
            return '{'
        data = json.loads(await DevelopmentRecipeProvider().generate(request))
        data['ingredients'] = [dict(name=name, quantity=100., unit='g') for name in request.selected_ingredients]
        data['instructions'] = ['Synthetic contract fixture; not a cooking recommendation.']
        if scenario == 'schema':
            data['ingredients'] = []
        elif scenario == 'conflict':
            data['ingredients'].append(dict(name='milk', quantity=100., unit='g'))
        elif scenario == 'state':
            data['ingredients'][0]['name'] = 'broccoli raw cooked'
        elif scenario == 'omit':
            data['ingredients'] = data['ingredients'][1:]
        return json.dumps(data)


class EvaluationNutritionProvider:
    def __init__(self, scenario):
        self.scenario = scenario

    async def lookup(self, ingredient):
        if self.scenario == 'unavailable':
            raise NutritionProviderError('Synthetic outage')
        if ingredient.canonical_name is None:
            return None
        return FoodRecord(food_id='SYNTHETIC-NOT-USDA', description='Evaluation arithmetic only',
            data_type='Foundation', retrieved_at='2000-01-01T00:00:00Z', food_state=ingredient.food_state,
            nutrients_per_100g=NutrientValues(calories=100., protein=10., carbohydrates=15.,
                fat=5., fiber=2., sodium=20., sugar=1.))
