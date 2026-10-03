from typing import Protocol
from app.schemas.intelligence import FoodRecord, NormalizedIngredient


class NutritionProviderError(Exception):
    """Public, redacted reason; raw HTTP exceptions must not be exposed or logged."""


class NutritionProvider(Protocol):
    async def lookup(self, ingredient: NormalizedIngredient) -> FoodRecord | None:
        """Return a reliable food match or None; never substitute a guessed food."""
        ...
