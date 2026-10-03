import asyncio
from uuid import uuid4
from pydantic import ValidationError
from app.core.errors import GenerationError
from app.schemas.recipes import RecipeCandidate, GeneratedRecipe
from app.schemas.repair import RecipeRepairRequest, RecipeRepairResponse, RepairChange
from app.services.normalization import IngredientNormalizationService
from app.services.constraints import ConstraintService
from app.providers.base import RepairProvider
from app.services.nutrition import NutritionService


HARD = {'allergy', 'excluded_ingredient', 'dietary_preference'}
MACRO_DIETS = {'high-protein', 'low-carb'}


def hard(result):
    return result.constraint in HARD and not (result.constraint == 'dietary_preference' and result.requested in MACRO_DIETS)


def score(intelligence):
    """Unknown count first, then normalized numeric distance; lower is better."""
    unknown = sum(r.status == 'unknown' for r in intelligence.constraint_results)
    distance = 0.0
    for r in intelligence.constraint_results:
        if r.status == 'failed':
            if isinstance(r.actual, (float, int)) and isinstance(r.requested, (float, int)):
                distance += abs(r.actual - r.requested) / (abs(r.requested) or 1.0)
            elif not hard(r) and r.constraint != 'dietary_preference':
                distance += 1.0
    return unknown, distance


def eligible(original, proposed, before, after):
    if any(hard(r) and r.status == 'failed' for r in after.constraint_results):
        return False
    prior = {(r.constraint, r.requested): r for r in before.constraint_results}
    for r in after.constraint_results:
        old = prior.get((r.constraint, r.requested))
        if old and old.status != 'unknown' and r.status == 'unknown':
            return False
    # Generic food data cannot certify allergies/free-from claims. When hard evidence
    # remains unknown, allow quantity/method changes only, never new ingredient names.
    if any(hard(r) and r.status == 'unknown' for r in after.constraint_results):
        names = {i.name.casefold().strip() for i in original.ingredients}
        if any(i.name.casefold().strip() not in names for i in proposed.ingredients):
            return False
    return True


def changes_between(before, after, targets):
    changes = []
    reason = 'Adjusted to address: ' + ', '.join(sorted({r.constraint.replace('_', ' ') for r in targets})) + '.'
    def grouped(recipe):
        result = {}
        for i in recipe.ingredients:
            result.setdefault(i.name, []).append(f'{i.quantity:g} {i.unit}')
        return {k: ' + '.join(v) for k, v in result.items()}
    left, right = grouped(before), grouped(after)
    for name in sorted(left.keys() | right.keys()):
        if left.get(name) != right.get(name):
            changes.append(RepairChange(ingredient=name, before=left.get(name, 'Not included'),
                after=right.get(name, 'Removed'), reason=reason))
    for field in ('instructions', 'prep_time', 'cook_time', 'title', 'description'):
        a, b = getattr(before, field), getattr(after, field)
        if a != b:
            changes.append(RepairChange(ingredient=field.replace('_', ' ').capitalize(),
                before=' '.join(a) if isinstance(a, list) else str(a),
                after=' '.join(b) if isinstance(b, list) else str(b), reason=reason))
    return changes


class RecipeRepairService:
    def __init__(self, provider: RepairProvider, nutrition_service: NutritionService, max_attempts=2, timeout_seconds=100):
        self.provider, self.nutrition = provider, nutrition_service
        self.max_attempts = min(2, max(0, max_attempts))
        self.timeout_seconds = timeout_seconds
        self.normalizer, self.constraints = IngredientNormalizationService(), ConstraintService()

    async def evaluate(self, recipe, request, deadline):
        normalized = [self.normalizer.normalize(i.name, i.quantity, i.unit) for i in recipe.ingredients]
        nutrition = await self.nutrition.calculate(normalized, recipe.servings,
            remaining_seconds=max(0, deadline - asyncio.get_running_loop().time()))
        return self.constraints.validate(request, recipe, nutrition)

    async def repair(self, payload: RecipeRepairRequest, trace_id: str):
        original, request = payload.recipe.model_copy(deep=True), payload.constraints
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        before = await self.evaluate(original, request, deadline)
        best, after = original, before
        failed = [r for r in before.constraint_results if r.status == 'failed']
        attempts, failure = 0, None
        for _ in range(self.max_attempts if failed else 0):
            if asyncio.get_running_loop().time() >= deadline:
                failure = 'repair_timeout'
                break
            attempts += 1
            # All verification comes from the server's fresh evaluation, never the caller.
            data = {'current_recipe': best.model_dump(),
                    'calculated_nutrition': after.calculated_nutrition.per_serving.model_dump(),
                    'failed_constraints': [dict(constraint=r.constraint, requested=r.requested, actual=r.actual)
                                           for r in after.constraint_results if r.status == 'failed'],
                    'original_preferences': request.model_dump()}
            try:
                async with asyncio.timeout(min(45, max(0, deadline - asyncio.get_running_loop().time()))):
                    proposal = RecipeCandidate.model_validate_json(await self.provider.repair(data))
                    if (proposal.servings != original.servings or proposal.cuisine != original.cuisine
                            or proposal.difficulty != original.difficulty):
                        raise ValueError('Protected recipe fields changed')
                    evaluated = await self.evaluate(proposal, request, deadline)
            except GenerationError as exc:
                failure = exc.code
                break
            except TimeoutError:
                failure = 'repair_timeout'
                break
            except (ValidationError, ValueError, TypeError):
                failure = 'invalid_repair_output'
                break
            if not eligible(original, proposal, before, evaluated):
                failure = 'unsafe_or_unverifiable_repair'
                continue
            best_eligible = eligible(original, best, before, after)
            if not best_eligible or score(evaluated) < score(after):
                best, after = proposal, evaluated
                failure = None
            if after.overall_constraint_status == 'passed':
                break
        improved = best is not original
        status = ('not_needed' if not failed else 'repaired' if improved and after.overall_constraint_status == 'passed'
                  else 'partially_repaired' if improved else 'failed')
        messages = {'not_needed': 'No failed constraints to optimize. Unknown checks remain unverified.',
                    'repaired': 'The selected recipe passes the calculated constraint checks.',
                    'partially_repaired': 'A better attempt was retained. Some checks still fail or remain unknown.',
                    'failed': 'No eligible improvement was found. The original recipe is preserved.'}
        if failure in ('provider_failure', 'provider_unavailable', 'provider_not_configured'):
            messages[status] += ' The recipe AI is temporarily unavailable. Please try again.'
        recipe_id = uuid4()
        original_generated = GeneratedRecipe(**original.model_dump(), id=recipe_id, recipe_version_id=uuid4())
        final_generated = GeneratedRecipe(**best.model_dump(), id=uuid4(), recipe_version_id=uuid4()) if improved else original_generated
        return RecipeRepairResponse(repair_status=status, repair_attempts=attempts,
            original_recipe=original_generated, final_recipe=final_generated,
            before_intelligence=before, after_intelligence=after,
            changes=changes_between(original, best, failed) if improved else [],
            remaining_failed_constraints=[r for r in after.constraint_results if r.status == 'failed'],
            message=messages[status], failure_code=failure, trace_id=trace_id)
