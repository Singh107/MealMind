from typing import Annotated
from pydantic import Field, model_validator
from app.schemas.recipes import Contract, RecipeCandidate, RecipeGenerationRequest, Name

class SubstitutionRequest(Contract):
    recipe: RecipeCandidate
    ingredient_index: Annotated[int, Field(ge=0, le=49)]
    restrictions: RecipeGenerationRequest

    @model_validator(mode='after')
    def index_exists(self):
        if self.ingredient_index >= len(self.recipe.ingredients):
            raise ValueError('Ingredient does not exist.')
        return self

class SubstitutionPreviewRequest(SubstitutionRequest):
    relationship_id: Name
    quantity: Annotated[float, Field(gt=0, le=100000, allow_inf_nan=False)] | None = None
    unit: Name | None = None
