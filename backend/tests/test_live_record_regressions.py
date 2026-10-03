"""Offline regressions captured from real providers on 2026-09-12 UTC.

The two-food calibration is explicitly a test case, not a repaired/generated meal.
No test makes network calls.
"""
import json
import unittest
from pathlib import Path
from app.schemas.recipes import RecipeCandidate, RecipeGenerationRequest, RecipeGenerationResponse
from app.services.nutrition import NutritionService
from app.services.constraints import ConstraintService

CAPTURED = json.loads((Path(__file__).parent / 'fixtures/live-nutrition-response.json').read_text())


class RecordedProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_captured_partial_math_and_unknown_constraints(self):
        response = RecipeGenerationResponse.model_validate_json(json.dumps(CAPTURED))
        sources = response.nutrition_sources
        class RecordedProvider:
            async def lookup(self, ingredient):
                return next((s.food for s in sources if s.ingredient.name == ingredient.name), None)
        result = await NutritionService(RecordedProvider()).calculate([s.ingredient for s in sources], 2)
        self.assertEqual(result.calculated_nutrition, response.calculated_nutrition)
        self.assertEqual(result.nutrition_status, 'partial')
        recipe = RecipeCandidate.model_validate({key: CAPTURED['recipe'][key] for key in RecipeCandidate.model_fields})
        result = ConstraintService().validate(RecipeGenerationRequest(selected_ingredients=['chicken'], calorie_target=300, protein_target=60), recipe, result)
        self.assertTrue(all(r.passed is None for r in result.constraint_results))

    async def test_real_food_record_calibration_pass_and_fail(self):
        response = RecipeGenerationResponse.model_validate_json(json.dumps(CAPTURED))
        sources = [s for s in response.nutrition_sources if s.status == 'calculated']
        class RecordedProvider:
            async def lookup(self, ingredient):
                return next(s.food for s in sources if s.ingredient.name == ingredient.name)
        result = await NutritionService(RecordedProvider()).calculate([s.ingredient for s in sources], 2)
        self.assertEqual(result.nutrition_status, 'verified')
        recipe = RecipeCandidate.model_validate({key: CAPTURED['recipe'][key] for key in RecipeCandidate.model_fields})
        # Only numeric metadata is used here; this is a arithmetic calibration,
        # not a claim that unmatched original ingredients have disappeared.
        engine = ConstraintService()
        passing = engine.validate(RecipeGenerationRequest(selected_ingredients=['chicken'], calorie_target=300, protein_target=35, max_cooking_time=30), recipe, result.model_copy(deep=True))
        self.assertEqual(passing.overall_constraint_status, 'passed')
        failing = engine.validate(RecipeGenerationRequest(selected_ingredients=['chicken'], calorie_target=250, protein_target=60), recipe, result.model_copy(deep=True))
        self.assertEqual(failing.overall_constraint_status, 'failed')
        self.assertTrue(all(r.passed is False for r in failing.constraint_results))
        self.assertAlmostEqual(failing.constraint_results[0].actual, 284.7539725)
        self.assertAlmostEqual(failing.constraint_results[1].actual, 39.41875)
