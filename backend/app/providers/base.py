from typing import Protocol
from app.schemas.recipes import RecipeGenerationRequest


class RecipeProvider(Protocol):
    name: str
    model: str

    async def generate(self, request: RecipeGenerationRequest) -> str:
        """Return a JSON candidate, never markdown. Service validates independently."""
        ...


class RepairProvider(Protocol):
    async def repair(self, payload: dict) -> str:
        """Propose structured content; the repair service validates and evaluates it."""
        ...
