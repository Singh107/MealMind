import asyncio
from uuid import uuid4
from pydantic import ValidationError
from app.core.errors import GenerationError
from app.providers.base import RecipeProvider
from app.providers.prompts import PROMPT_VERSION
from app.schemas.recipes import (GeneratedRecipe, GenerationMetadata, RecipeCandidate,
                                 RecipeGenerationRequest, RecipeGenerationResponse)
from app.services.normalization import IngredientNormalizationService
from app.services.nutrition import NutritionService
from app.services.constraints import ConstraintService
from app.providers.usda import USDAFoodDataCentralProvider
from app.core.config import Settings



class RecipeService:
    def __init__(self, provider: RecipeProvider, timeout_seconds: float = 45,
                 nutrition_service: NutritionService | None = None):
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.normalizer = IngredientNormalizationService()
        self.nutrition_service = nutrition_service or NutritionService(USDAFoodDataCentralProvider(Settings()))
        self.constraints = ConstraintService()

    async def generate(self, request: RecipeGenerationRequest, trace_id: str) -> RecipeGenerationResponse:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        try:
            async with asyncio.timeout(self.timeout_seconds):
                raw = await self.provider.generate(request)
            candidate = RecipeCandidate.model_validate_json(raw)
        except TimeoutError as exc:
            raise GenerationError('provider_timeout', 'Recipe generation timed out. Please try again.', 504) from exc
        except (ValidationError, ValueError, TypeError) as exc:
            raise GenerationError('invalid_provider_output', 'The provider returned an invalid recipe. Please retry.') from exc
        if candidate.servings != request.servings:
            raise GenerationError('invalid_provider_output', 'The generated servings did not match your request. Please retry.')
        normalized = [self.normalizer.normalize(item.name, item.quantity, item.unit) for item in candidate.ingredients]
        intelligence = await self.nutrition_service.calculate(normalized, candidate.servings,
            remaining_seconds=max(0, deadline - asyncio.get_running_loop().time()))
        intelligence = self.constraints.validate(request, candidate, intelligence)
        recipe = GeneratedRecipe(**candidate.model_dump(), id=uuid4(), recipe_version_id=uuid4())
        return RecipeGenerationResponse(
            evaluated_request=request,
            recipe=recipe,
            warnings=['Legacy recipe.nutrition contains AI estimates; calculated_nutrition is independent food-data arithmetic.',
                      'Generic food data does not establish allergen safety. Check ingredients and product labels.',
                      'Additional ingredients may be included; review the complete ingredient list.'],
            metadata=GenerationMetadata(provider=self.provider.name, model=self.provider.model, prompt_version=PROMPT_VERSION),
            trace_id=trace_id, **intelligence.model_dump())
