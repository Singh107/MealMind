from app.schemas.intelligence import ConstraintResult, RecipeIntelligence
from app.schemas.recipes import RecipeCandidate, RecipeGenerationRequest
from app.services.ingredient_catalog import clean_name, identity_for, related_identity

ALLERGY_ALIASES = {'nuts': 'tree nuts', 'nut': 'tree nuts', 'tree nut': 'tree nuts',
                   'dairy': 'milk', 'egg': 'eggs', 'peanut': 'peanuts', 'soya': 'soy'}
# Explicit ingredient evidence is used for potential conflicts, not absence certification.
ALLERGEN_WORDS = {'milk': ('milk', 'cheese', 'butter', 'yogurt', 'yoghurt', 'cream', 'whey', 'casein'),
    'eggs': ('egg', 'eggs', 'albumen'), 'peanuts': ('peanut', 'peanuts'),
    'tree nuts': ('almond', 'almonds', 'walnut', 'walnuts', 'cashew', 'cashews', 'pecan', 'hazelnut', 'pistachio'),
    'soy': ('soy', 'soya', 'tofu', 'edamame'), 'shellfish': ('shrimp', 'prawn', 'prawns', 'crab', 'lobster', 'clam', 'oyster'),
    'fish': ('fish', 'salmon', 'tuna', 'cod', 'anchovy'), 'sesame': ('sesame', 'tahini'),
    'wheat': ('wheat', 'semolina', 'bulgur', 'couscous'), 'gluten': ('wheat', 'barley', 'rye', 'semolina', 'bulgur', 'couscous')}


def phrase_in(phrase: str, text: str) -> bool:
    return f' {clean_name(phrase)} ' in f' {clean_name(text)} '


class ConstraintService:
    def validate(self, request: RecipeGenerationRequest, recipe: RecipeCandidate,
                 intelligence: RecipeIntelligence) -> RecipeIntelligence:
        results: list[ConstraintResult] = []
        nutrients = intelligence.calculated_nutrition.per_serving
        sources = intelligence.nutrition_sources
        evidence = [f'usda_fdc:{source.food.food_id}' for source in sources if source.food]

        def numeric(name, target, actual, unit, minimum=False):
            passed = None if actual is None else actual >= target if minimum else actual <= target
            results.append(ConstraintResult(constraint=name, requested=target, actual=actual, unit=unit,
                passed=passed, status='unknown' if passed is None else 'passed' if passed else 'failed',
                difference=None if actual is None else actual - target,
                reason=('Insufficient calculated nutrient coverage; the AI estimate is not used.' if actual is None else
                        ('At or above the inclusive minimum.' if minimum else 'At or below the inclusive maximum.') if passed else
                        ('Below the requested minimum.' if minimum else 'Above the requested maximum.')),
                evidence=['recipe:estimated_cook_time'] if name == 'maximum_cooking_time' else evidence))

        for name, target, bounds, actual, unit in [
            ('calories', request.calorie_target, request.calorie_range, nutrients.calories, 'kcal'),
            ('carbohydrates', request.carbs_target, request.carbs_range, nutrients.carbohydrates, 'g'),
            ('fat', request.fat_target, request.fat_range, nutrients.fat, 'g')]:
            if target is not None:
                numeric(f'maximum_{name}', target, actual, unit)
            if bounds:
                if bounds.minimum is not None:
                    numeric(f'minimum_{name}', bounds.minimum, actual, unit, True)
                if bounds.maximum is not None:
                    numeric(f'maximum_{name}', bounds.maximum, actual, unit)
        if request.protein_target is not None:
            numeric('minimum_protein', request.protein_target, nutrients.protein, 'g', True)
        if request.max_cooking_time is not None:
            numeric('maximum_cooking_time', request.max_cooking_time, recipe.cook_time, 'minutes')

        known = [identity_for(source.ingredient.name) for source in sources]
        names = [ingredient.name for ingredient in recipe.ingredients]

        def qualitative(constraint, requested, conflict, complete, reason):
            passed = False if conflict else True if complete else None
            results.append(ConstraintResult(constraint=constraint, requested=requested,
                actual=', '.join(conflict) if conflict else None,
                passed=passed, status='failed' if conflict else 'passed' if complete else 'unknown',
                reason=reason, evidence=['ingredient-vocabulary-v1']))

        for exclusion in request.excluded_ingredients:
            excluded_identity = identity_for(exclusion)
            conflicts = [name for name, identity in zip(names, known) if phrase_in(exclusion, name)
                         or (excluded_identity and identity and excluded_identity.name == identity.name)]
            uncertain_family = excluded_identity and any(identity and related_identity(identity.name, excluded_identity.name)
                                                        for identity in known)
            complete = all(known) and not uncertain_family
            qualitative('excluded_ingredient', exclusion, conflicts, complete,
                'Excluded ingredient detected.' if conflicts else
                'Related ingredient specificity is uncertain; check the exclusion manually.' if uncertain_family else
                'No match in the supported whole-ingredient vocabulary.' if complete else
                'Unable to verify exclusions in unrecognized or composite ingredients.')

        warnings = []
        for allergy in request.allergies:
            canonical = ALLERGY_ALIASES.get(clean_name(allergy), clean_name(allergy))
            terms = ALLERGEN_WORDS.get(canonical, (canonical,))
            conflicts = [name for name, identity in zip(names, known) if
                         (identity and canonical in identity.allergens) or any(phrase_in(term, name) for term in terms)]
            qualitative('allergy', allergy, conflicts, False,
                'Potential allergen detected from ingredient evidence.' if conflicts else
                'Unable to verify absence of allergens or cross-contact from generic food records; check product labels.')
            warnings.append(f'Potential allergen: {allergy} in {", ".join(conflicts)}.' if conflicts else f'Unable to verify allergy restriction: {allergy}.')

        for diet in request.dietary_preferences:
            if diet in ('high-protein', 'low-carb', 'keto'):
                matching = [r for r in results if r.constraint == ('minimum_protein' if diet == 'high-protein' else 'maximum_carbohydrates')]
                result = matching[0] if matching else None
                # Keto requires a full documented ruleset, beyond a carbohydrate maximum.
                passed = result.passed if result and diet != 'keto' else None
                results.append(ConstraintResult(constraint='dietary_preference', requested=diet, actual=None,
                    status='unknown' if passed is None else 'passed' if passed else 'failed', passed=passed,
                    reason='Evaluated against your explicit nutrient bound.' if passed is not None else
                    'No complete explicit ruleset/target for this dietary label; unable to verify.'))
                continue
            forbidden_categories = {'vegan': {'meat', 'fish', 'shellfish', 'dairy', 'egg', 'honey'},
                                    'vegetarian': {'meat', 'fish', 'shellfish'}, 'pescatarian': {'meat'}}.get(diet, set())
            allergen_set = {'dairy-free': {'milk'}, 'gluten-free': {'gluten', 'wheat'},
                            'nut-free': {'tree nuts', 'peanuts'}}.get(diet, set())
            conflicts = [name for name, identity in zip(names, known) if identity and
                         (identity.category in forbidden_categories or bool(set(identity.allergens) & allergen_set))]
            # Free-from claims require label/cross-contact evidence; no positive certification.
            complete = bool(forbidden_categories) and all(known)
            qualitative('dietary_preference', diet, conflicts, complete,
                'Ingredient composition conflicts with this preference.' if conflicts else
                'Supported ingredient composition meets the selected diet; no certification implied.' if complete else
                'Unable to verify this dietary preference for all ingredients and product labels.')
        for allergen in recipe.potential_allergens:
            warnings.append(f'AI-reported potential allergen (unverified): {allergen}.')
        intelligence.constraint_results = results
        intelligence.overall_constraint_status = ('failed' if any(r.passed is False for r in results) else
            'partially_verified' if not results or any(r.passed is None for r in results) or intelligence.nutrition_status != 'verified' else 'passed')
        intelligence.potential_allergen_warnings = warnings
        return intelligence
