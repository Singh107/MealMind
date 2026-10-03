"""Load current account defaults without trusting client-owned restrictions."""
from pydantic import ValidationError
from app.db.repositories import UserPreferencesRepository
from app.schemas.persistence import PreferencesInput
from app.schemas.recipes import RecipeGenerationRequest
from app.core.errors import GenerationError


async def generation_context(request, user, settings):
    if user is None:
        return request
    row = await UserPreferencesRepository(settings, user).get()
    prefs = PreferencesInput.model_validate({k: row[k] for k in PreferencesInput.model_fields} if row else {})
    return merge_preferences(request, prefs)


def merge_preferences(request, prefs):
    values = request.model_dump()
    for field in ('dietary_preferences', 'allergies', 'excluded_ingredients'):
        combined = getattr(prefs, field) + values[field]
        values[field] = list({x.casefold(): x for x in reversed(combined)}.values())
    for nutrient in ('calorie', 'carbs', 'fat'):
        target, bounds = nutrient + '_target', nutrient + '_range'
        if values[target] is None and values[bounds] is None:
            values[target] = prefs.nutrition_targets.get(target)
            values[bounds] = prefs.nutrition_targets.get(bounds)
    if values['protein_target'] is None:
        values['protein_target'] = prefs.nutrition_targets.get('protein_target')
    for field, value in prefs.cooking_preferences.items():
        if values[field] is None or field not in request.model_fields_set:
            values[field] = value
    if not values['cuisine'] and prefs.preferred_cuisines:
        values['cuisine'] = prefs.preferred_cuisines[0]
    try:
        return RecipeGenerationRequest.model_validate(values)
    except ValidationError:
        raise GenerationError('preference_conflict', 'Selected ingredients or controls conflict with your saved preferences. Review Profile and Recipe Studio.', 422, False) from None
