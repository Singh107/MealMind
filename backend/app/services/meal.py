import asyncio
from uuid import uuid4
from pydantic import ValidationError
from app.core.errors import GenerationError
from app.services.vision import prepare_image
from app.services.normalization import IngredientNormalizationService
from app.services.pantry import pantry_identity
from app.schemas.meal import MealVisionProposal, MealVisionAnalysis, MealComponent, MealNutritionAnalysis


class MealVisionService:
    def __init__(self, provider, timeout=45):
        self.provider, self.timeout = provider, timeout

    async def analyze(self, data, mime):
        image = await asyncio.to_thread(prepare_image, data, mime)
        try:
            async with asyncio.timeout(self.timeout):
                raw = await self.provider.analyze(image, 'image/jpeg')
            proposal = MealVisionProposal.model_validate_json(raw)
        except TimeoutError as exc:
            raise GenerationError('vision_timeout', 'Meal identification timed out. Please try again.', 504) from exc
        except (ValidationError, ValueError, TypeError) as exc:
            raise GenerationError('vision_invalid_output', 'The meal could not be identified reliably. Please review it manually.') from exc
        components = []
        for item in proposal.components:
            name = item.display_name + (f', {item.visible_state}' if item.visible_state else '')
            normalized = IngredientNormalizationService().normalize(name, 1, 'g')
            identity = pantry_identity(name)
            components.append(MealComponent(**item.model_dump(), normalized_name=identity['normalized_name'],
                canonical_name=normalized.canonical_name, food_state=normalized.food_state,
                identity_status='conflicting' if normalized.reason == 'Conflicting food preparation states.' else identity['identity_status']))
        return MealVisionAnalysis(analysis_id=str(uuid4()), meal_name=proposal.meal_name, components=components,
            limitations=['Review the suggested foods and preparation. Confidence is qualitative self-assessment.',
                        'Enter consumed amounts yourself. Photos do not establish nutrition, hidden ingredients or safety.'])


class MealNutritionService:
    def __init__(self, nutrition):
        self.nutrition = nutrition

    async def calculate(self, request):
        normalized = [IngredientNormalizationService().normalize(c.name, c.quantity, c.unit) for c in request.components]
        # One entered meal: all quantities are consumed amounts, never inferred servings.
        result = await self.nutrition.calculate(normalized, servings=1)
        return MealNutritionAnalysis(analysis_id=str(uuid4()), nutrition=result)
