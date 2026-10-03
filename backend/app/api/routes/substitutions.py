from fastapi import APIRouter, Depends
from app.core.auth import bearer, authenticated_user
from app.core.config import get_settings
from app.core.errors import GenerationError
from app.db.repositories import UserPreferencesRepository
from app.db.pantry import PantryRepository
from app.schemas.persistence import PreferencesInput
from app.schemas.recipes import RecipeGenerationRequest
from app.schemas.substitutions import SubstitutionRequest, SubstitutionPreviewRequest
from app.services.substitutions import SubstitutionService
from app.services.nutrition import NutritionService
from app.services.nutrition_cache import CachedNutritionProvider
from app.providers.usda import USDAFoodDataCentralProvider
from app.api.routes.recipes import get_food_cache
from app.services.generation_preferences import merge_preferences

router=APIRouter(prefix='/api/ingredients/substitutions',tags=['substitutions'])

async def optional_user(credentials=Depends(bearer),settings=Depends(get_settings)):
    return await authenticated_user(credentials,settings) if credentials else None

async def restrictions_for(payload,user,settings):
    if user is None:
        return payload.restrictions
    row=await UserPreferencesRepository(settings,user).get()
    prefs=PreferencesInput.model_validate({k:row[k] for k in PreferencesInput.model_fields} if row else {})
    # Keep recipe-specific restrictions as well as current account restrictions.
    return merge_preferences(payload.restrictions.model_copy(update={'selected_ingredients':['preference validation']}), prefs)

async def preview_service(settings=Depends(get_settings)):
    async with USDAFoodDataCentralProvider(settings) as provider:
        nutrition=NutritionService(CachedNutritionProvider(provider,get_food_cache(settings.nutrition_cache_ttl_seconds,settings.nutrition_cache_max_entries)),settings.nutrition_timeout_seconds)
        yield SubstitutionService(nutrition)

@router.post('')
async def browse(payload:SubstitutionRequest,user=Depends(optional_user),settings=Depends(get_settings)):
    restrictions=await restrictions_for(payload,user,settings)
    pantry,state=None,'signed_out'
    if user:
        try:
            pantry=await PantryRepository(settings,user).list()
            state='loaded'
        except GenerationError:
            state='unavailable'
    return SubstitutionService().browse(payload,restrictions,pantry,state)

@router.post('/preview')
async def preview(payload:SubstitutionPreviewRequest,user=Depends(optional_user),settings=Depends(get_settings),service=Depends(preview_service)):
    restrictions=await restrictions_for(payload,user,settings)
    return await service.preview(payload,restrictions)
