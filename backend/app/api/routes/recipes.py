from app.schemas.repair import RecipeRepairRequest, RecipeRepairResponse
from app.services.repair import RecipeRepairService
from fastapi import APIRouter, Depends, Request
from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse
from app.providers.gemini import GeminiRecipeProvider
from app.schemas.recipes import RecipeGenerationRequest, RecipeGenerationResponse
from app.services.recipes import RecipeService
from app.providers.usda import USDAFoodDataCentralProvider
from app.services.nutrition import NutritionService
from app.services.nutrition_cache import CachedNutritionProvider, InMemoryFoodCache
from functools import lru_cache
from app.core.auth import bearer, authenticated_user
from app.services.generation_preferences import generation_context

router = APIRouter(prefix='/api/recipes', tags=['recipes'])

async def generation_user(credentials=Depends(bearer), settings=Depends(get_settings)):
    return await authenticated_user(credentials, settings) if credentials else None


@lru_cache(maxsize=4)
def get_food_cache(ttl_seconds: int, max_entries: int) -> InMemoryFoodCache:
    return InMemoryFoodCache(ttl_seconds, max_entries)


async def get_recipe_service(settings: Settings = Depends(get_settings)):
    # One connection pool per generation request, closed even on cancellation.
    async with USDAFoodDataCentralProvider(settings) as provider:
        nutrition = NutritionService(CachedNutritionProvider(provider,
            get_food_cache(settings.nutrition_cache_ttl_seconds, settings.nutrition_cache_max_entries)), settings.nutrition_timeout_seconds)
        if settings.dev_mock_ai:
            from app.providers.dev_fixture import DevelopmentRecipeProvider
            ai_provider = DevelopmentRecipeProvider()
        else:
            ai_provider = GeminiRecipeProvider(settings)
        yield RecipeService(ai_provider, settings.generation_timeout_seconds, nutrition)


@router.post('/generate', response_model=RecipeGenerationResponse,
             responses={code: {'model': ErrorResponse} for code in (422, 429, 500, 502, 503, 504)})
async def generate_recipe(payload: RecipeGenerationRequest, request: Request,
                          service: RecipeService = Depends(get_recipe_service),
                          user=Depends(generation_user), settings: Settings = Depends(get_settings)):
    payload = await generation_context(payload, user, settings)
    return await service.generate(payload, request.state.trace_id)




@router.post('/repair', response_model=RecipeRepairResponse)
async def repair_recipe(payload: RecipeRepairRequest, request: Request,
                        service: RecipeService = Depends(get_recipe_service),
                        settings: Settings = Depends(get_settings)):
    repair = RecipeRepairService(service.provider, service.nutrition_service,
                                 settings.max_repair_attempts, settings.repair_timeout_seconds)
    return await repair.repair(payload, request.state.trace_id)
