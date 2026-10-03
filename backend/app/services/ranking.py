"""Deterministic evaluation of owner-scoped saved snapshots; no provider calls."""
import json
from pydantic import ValidationError
from app.schemas.recipes import GeneratedRecipe, RecipeGenerationRequest
from app.schemas.persistence import PreferencesInput
from app.schemas.intelligence import RecipeIntelligence, CalculatedNutrition, IngredientNutrition, NutrientValues
from app.services.normalization import IngredientNormalizationService
from app.services.constraints import ConstraintService
from app.services.pantry import PantryService, pantry_identity


class RankingService:
    @staticmethod
    def evidence(recipe, snapshot):
        normalizer = IngredientNormalizationService()
        sources = [IngredientNutrition(ingredient_index=i, ingredient=normalizer.normalize(x.name, x.quantity, x.unit),
                   status='unavailable') for i, x in enumerate(recipe.ingredients)]
        result = RecipeIntelligence(calculated_nutrition=CalculatedNutrition(servings=recipe.servings,
            ingredient_count=len(sources)), nutrition_status='unavailable', nutrition_sources=sources,
            unmatched_ingredients=[x.name for x in recipe.ingredients])
        try:
            saved = RecipeIntelligence.model_validate(snapshot.get('intelligence'))
            calc = saved.calculated_nutrition
            aligned = calc.servings == recipe.servings and calc.ingredient_count == len(sources) and len(saved.nutrition_sources) == len(sources)
            aligned = aligned and all(old.ingredient_index == i and
                old.ingredient.name == new.ingredient.name and old.ingredient.food_state == new.ingredient.food_state and
                old.ingredient.quantity == new.ingredient.quantity and old.ingredient.unit == new.ingredient.unit
                for i, (old, new) in enumerate(zip(saved.nutrition_sources, sources)))
            if aligned and saved.nutrition_status != 'unavailable':
                for name in NutrientValues.model_fields:
                    if calc.coverage.get(name) == len(sources):
                        setattr(result.calculated_nutrition.per_serving, name, getattr(calc.per_serving, name))
                result.nutrition_status = saved.nutrition_status
        except (ValidationError, TypeError, AttributeError):
            pass
        return result

    def rank(self, rows, pantry, preferences: PreferencesInput, limit=20, offset=0):
        evaluated = []
        skipped = 0
        ineligible = 0
        for row in rows:
            snapshot = row.get('recipe', {}).get('structuredRecipe')
            try:
                if not isinstance(snapshot, dict):
                    raise ValueError('No structured candidate')
                recipe = GeneratedRecipe.model_validate_json(json.dumps({k: snapshot[k] for k in GeneratedRecipe.model_fields if k in snapshot}))
            except (ValidationError, ValueError, TypeError):
                skipped += 1
                continue
            # Neutral selection validates preferences without rejecting the candidate before evaluation.
            request = RecipeGenerationRequest.model_validate(dict(selected_ingredients=['preference validation'],
                dietary_preferences=preferences.dietary_preferences, allergies=preferences.allergies,
                excluded_ingredients=preferences.excluded_ingredients,
                **preferences.nutrition_targets, **preferences.cooking_preferences))
            report = ConstraintService().validate(request, recipe, self.evidence(recipe, snapshot))
            checks = report.constraint_results
            hard = [r for r in checks if r.constraint in ('allergy', 'excluded_ingredient') or
                    (r.constraint == 'dietary_preference' and r.requested not in ('high-protein', 'low-carb', 'keto'))]
            if any(r.status == 'failed' for r in hard):
                ineligible += 1
                continue
            fit = PantryService.compare(recipe.ingredients, pantry)
            uncertain = fit.unknown_count > 0 or any(r.status == 'unknown' for r in checks)
            passed = sum(r.status == 'passed' for r in checks)
            failed = sum(r.status == 'failed' for r in checks)
            soft = []
            if preferences.preferred_cuisines:
                soft.append(('Preferred cuisine', recipe.cuisine.strip().casefold() in [x.strip().casefold() for x in preferences.preferred_cuisines]))
            if preferences.cooking_preferences.get('difficulty'):
                soft.append(('Preferred difficulty', recipe.difficulty == preferences.cooking_preferences['difficulty']))
            components = dict(pantry_fit=60 * fit.available_count / fit.ingredient_count,
                constraints=15 * (passed - failed) / len(checks) if checks else 0,
                preferences=10 * sum(match for _, match in soft) / len(soft) if soft else 0,
                missing_penalty=-2 * min(fit.missing_count, 5),
                unknown_penalty=-5 * fit.unknown_count / fit.ingredient_count)
            reasons = [dict(code='pantry_presence', text=f'You have {fit.available_count} of {fit.ingredient_count} listed ingredients by name/state; quantities are not checked.')]
            for status, label in [('missing', 'Missing'), ('unknown', 'Check manually')]:
                names = [x.name for x in fit.ingredients if x.status == status]
                if names:
                    reasons.append(dict(code=status, text=label + ': ' + ', '.join(names) + '.'))
            for r in checks:
                label = r.constraint.replace('_', ' ')
                reasons.append(dict(code='constraint_' + r.status, text=f'{label} ({r.requested}): {r.status}. ' +
                    ('Based on saved nutrition evidence; not freshly recalculated.' if r.unit in ('kcal', 'g') else r.reason)))
            for label, match in soft:
                if match:
                    reasons.append(dict(code='preference_match', text=label + ' matches.'))
            evaluated.append(dict(saved_recipe_id=str(row['id']), recipe=snapshot,
                eligibility='uncertain' if uncertain else 'eligible', score=round(sum(components.values()), 1),
                components={k: round(v, 2) for k, v in components.items()}, pantry=fit.model_dump(mode='json'),
                constraints=[r.model_dump(mode='json') for r in checks], reasons=reasons))
        evaluated.sort(key=lambda x: (x['eligibility'] == 'uncertain', -x['score'], x['saved_recipe_id']))
        usable = sum(pantry_identity(x['name'])['identity_status'] == 'recognized' for x in pantry)
        state = ('empty_pantry' if not usable else 'no_candidates' if not evaluated and not ineligible else
                 'all_ineligible' if not evaluated else 'only_uncertain' if all(x['eligibility'] == 'uncertain' for x in evaluated) else 'ready')
        if not usable:
            evaluated = []
        for index, entry in enumerate(evaluated):
            entry['rank'] = index + 1
        return dict(state=state, source='your_saved_recipes', entries=evaluated[offset:offset + limit],
            total=len(evaluated), candidate_count=len(rows) - skipped, skipped_count=skipped,
            ineligible_count=ineligible, limit=limit, offset=offset,
            basis='Saved recipe snapshots and current preferences; name/state presence, not sufficient quantities or allergy certification.')
