from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.recipes import Name, RecipeIngredient
from app.services.normalization import normalize_unit


class PantryInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: Name
    quantity: Annotated[float, Field(gt=0, le=100000, strict=True)] | None = None
    unit: Name | None = None

    @field_validator('unit')
    @classmethod
    def supported_unit(cls, value):
        if value is None:
            return None
        unit = normalize_unit(value)
        if unit is None:
            raise ValueError('Choose a supported unit or leave it blank.')
        return unit


class PantryItem(PantryInput):
    id: UUID
    normalized_name: str
    food_state: str | None
    identity_status: Literal['recognized', 'unresolved']
    created_at: datetime
    updated_at: datetime


class CompatibilityInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ingredients: list[RecipeIngredient] = Field(min_length=1, max_length=50)


class IngredientAvailability(BaseModel):
    ingredient_index: int
    name: str
    status: Literal['available', 'missing', 'unknown']
    pantry_item_id: UUID | None = None
    reason: str
    quantity_status: Literal['sufficient', 'insufficient', 'unknown'] = 'unknown'
    quantity_reason: str = 'Check quantity; amounts are not safely comparable.'


class PantryCompatibility(BaseModel):
    pantry_count: int
    usable_pantry_count: int
    ingredient_count: int
    available_count: int
    missing_count: int
    unknown_count: int
    coverage_percent: float | None
    ingredients: list[IngredientAvailability]
    basis: str = 'Ingredient presence with separate conservative quantity checks; no substitution or allergy-safety claim.'
