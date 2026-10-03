"""Explicit development-only AI proposals; nutrition/constraints remain real services."""
from app.schemas.recipes import RecipeCandidate, RecipeGenerationRequest


class DevelopmentRecipeProvider:
    name = 'development-fixture'
    model = 'broccoli-oil-demo-v1'

    async def generate(self, request: RecipeGenerationRequest) -> str:
        # A fixed, prominently labeled scenario, not a personalized AI recipe.
        recipe = RecipeCandidate(
            title='[DEV FIXTURE] Broccoli and Olive Oil',
            description='Development fixture, not Gemini output. Fixed broccoli/oil scenario for testing generation and optimization.',
            ingredients=[{'name': 'Broccoli, raw', 'quantity': 300, 'unit': 'g'},
                         {'name': 'Olive oil', 'quantity': 40, 'unit': 'g'}],
            instructions=['Coat broccoli with the listed oil.', 'Roast until tender, checking regularly.'],
            prep_time=5, cook_time=30, total_time=35, servings=request.servings,
            cuisine=request.cuisine or 'simple', difficulty=request.difficulty or 'beginner',
            dietary_tags=[], potential_allergens=[],
            nutrition={'calories': None, 'protein': None, 'carbohydrates': None, 'fat': None})
        return recipe.model_dump_json()

    async def repair(self, payload: dict) -> str:
        original = RecipeCandidate.model_validate(payload['current_recipe'])
        data = original.model_dump()
        # Change only this known fixture; never pretend to optimize arbitrary user recipes.
        if original.title != '[DEV FIXTURE] Broccoli and Olive Oil':
            from app.core.errors import GenerationError
            raise GenerationError('invalid_repair_output', 'Development mode only optimizes its labeled fixture.', 422, False)
        targets = {r['constraint'] for r in payload['failed_constraints']}
        if targets & {'maximum_calories', 'maximum_fat'}:
            for ingredient in data['ingredients']:
                if ingredient['name'] == 'Olive oil':
                    ingredient['quantity'] = max(1, ingredient['quantity'] / 2)
        if 'maximum_cooking_time' in targets:
            data['cook_time'] = min(10, payload['original_preferences']['max_cooking_time'])
            data['total_time'] = data['prep_time'] + data['cook_time']
            data['instructions'] = ['Cut broccoli into small florets.',
                'Cook broccoli in a covered microwave-safe dish until tender; use the listed oil to finish.']
        return RecipeCandidate.model_validate(data).model_dump_json()
