from typing import Literal
from pydantic import model_validator
from app.schemas.recipes import Contract, RecipeCandidate, GeneratedRecipe, RecipeGenerationRequest
from app.schemas.intelligence import RecipeIntelligence, ConstraintResult


class RecipeRepairRequest(Contract):
    recipe: RecipeCandidate
    constraints: RecipeGenerationRequest

    @model_validator(mode='after')
    def same_servings(self):
        if self.recipe.servings != self.constraints.servings:
            raise ValueError('Recipe servings must match the original request.')
        return self


class RepairChange(Contract):
    ingredient: str
    before: str
    after: str
    reason: str


class RecipeRepairResponse(Contract):
    repair_status: Literal['not_needed', 'repaired', 'partially_repaired', 'failed']
    repair_attempts: int
    original_recipe: GeneratedRecipe
    final_recipe: GeneratedRecipe
    before_intelligence: RecipeIntelligence
    after_intelligence: RecipeIntelligence
    changes: list[RepairChange]
    remaining_failed_constraints: list[ConstraintResult]
    message: str
    failure_code: str | None = None
    trace_id: str
