from fastapi import APIRouter, Depends, Request
from app.core.config import get_settings
from app.api.routes.vision import read_image
from app.api.routes.recipes import get_food_cache
from app.providers.meal_vision import GeminiMealVisionProvider
from app.providers.usda import USDAFoodDataCentralProvider
from app.services.nutrition_cache import CachedNutritionProvider
from app.services.nutrition import NutritionService
from app.services.meal import MealVisionService, MealNutritionService
from app.schemas.meal import MealNutritionRequest, MealNutritionAnalysis, MealVisionAnalysis

router = APIRouter(tags=['meal-analysis'])


def get_meal_vision(settings=Depends(get_settings)):
    return MealVisionService(GeminiMealVisionProvider(settings), settings.generation_timeout_seconds)


async def get_meal_nutrition(settings=Depends(get_settings)):
    async with USDAFoodDataCentralProvider(settings) as provider:
        yield MealNutritionService(NutritionService(CachedNutritionProvider(provider,
            get_food_cache(settings.nutrition_cache_ttl_seconds, settings.nutrition_cache_max_entries)), settings.nutrition_timeout_seconds))


@router.post('/api/vision/meal', response_model=MealVisionAnalysis)
async def meal_vision(request: Request, service=Depends(get_meal_vision)):
    data, mime = await read_image(request)
    return await service.analyze(data, mime)


@router.post('/api/nutrition/meal', response_model=MealNutritionAnalysis)
async def meal_nutrition(payload: MealNutritionRequest, service=Depends(get_meal_nutrition)):
    return await service.calculate(payload)
