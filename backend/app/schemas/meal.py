from typing import Literal
from pydantic import Field, field_validator
from app.schemas.recipes import Contract, Name
from app.schemas.vision import DetectionProposal
from app.schemas.intelligence import RecipeIntelligence
from app.services.normalization import normalize_unit


class MealComponentProposal(DetectionProposal):
    visible_state: Literal['raw', 'cooked', 'dry', 'canned', 'fried', 'roasted', 'steamed', 'boiled', 'baked'] | None = None


class MealVisionProposal(Contract):
    meal_name: Name | None = None
    components: list[MealComponentProposal] = Field(max_length=30)


class MealComponent(MealComponentProposal):
    normalized_name: str
    canonical_name: str | None
    food_state: str | None
    identity_status: Literal['recognized', 'unresolved', 'conflicting']


class MealVisionAnalysis(Contract):
    analysis_id: str
    meal_name: Name | None
    components: list[MealComponent]
    limitations: list[str]


class ReviewedComponent(Contract):
    name: Name
    quantity: float = Field(gt=0, le=100000, allow_inf_nan=False)
    unit: Name

    @field_validator('unit')
    @classmethod
    def supported_unit(cls, value):
        unit = normalize_unit(value)
        if unit is None:
            raise ValueError('Choose a supported quantity unit.')
        return unit


class MealNutritionRequest(Contract):
    confirmed: Literal[True]
    components: list[ReviewedComponent] = Field(min_length=1, max_length=30)


class MealNutritionAnalysis(Contract):
    analysis_id: str
    basis: Literal['entered_consumed_amounts'] = 'entered_consumed_amounts'
    nutrition: RecipeIntelligence
