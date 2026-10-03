from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class NutrientValues(DataModel):
    """kcal, grams of macros/fiber, milligrams of sodium. Null means unknown."""
    calories: Annotated[float, Field(ge=0)] | None = None
    protein: Annotated[float, Field(ge=0)] | None = None
    carbohydrates: Annotated[float, Field(ge=0)] | None = None
    fat: Annotated[float, Field(ge=0)] | None = None
    fiber: Annotated[float, Field(ge=0)] | None = None
    sodium: Annotated[float, Field(ge=0)] | None = None
    sugar: Annotated[float, Field(ge=0)] | None = None


class NormalizedIngredient(DataModel):
    original_text: str
    name: str
    canonical_name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    normalized_unit: str | None = None
    preparation: str | None = None
    food_state: str | None = None
    grams: float | None = None
    status: Literal['normalized', 'needs_conversion', 'unresolved']
    reason: str | None = None
    conversion_evidence: str | None = None


class FoodPortion(DataModel):
    unit: str
    amount: Annotated[float, Field(gt=0)]
    gram_weight: Annotated[float, Field(gt=0)]
    description: str


class FoodRecord(DataModel):
    source: Literal['usda_fdc'] = 'usda_fdc'
    food_id: str
    description: str
    data_type: Literal['Foundation', 'SR Legacy']
    retrieved_at: str
    food_state: str | None = None
    match_quality: Literal['exact_name_and_state'] = 'exact_name_and_state'
    nutrients_per_100g: NutrientValues
    nutrient_ids: dict[str, int] = Field(default_factory=dict)
    portions: list[FoodPortion] = Field(default_factory=list)


class IngredientNutrition(DataModel):
    ingredient_index: int
    ingredient: NormalizedIngredient
    status: Literal['calculated', 'partial', 'unmatched', 'unavailable', 'unconvertible']
    food: FoodRecord | None = None
    nutrients: NutrientValues = Field(default_factory=NutrientValues)
    reason: str | None = None


class CalculatedNutrition(DataModel):
    # A nutrient is present in totals/per_serving only when every ingredient covers it.
    totals: NutrientValues = Field(default_factory=NutrientValues)
    per_serving: NutrientValues = Field(default_factory=NutrientValues)
    known_totals: NutrientValues = Field(default_factory=NutrientValues)
    known_per_serving: NutrientValues = Field(default_factory=NutrientValues)
    coverage: dict[str, int] = Field(default_factory=dict)
    ingredient_count: int = 0
    servings: int
    calculation_version: str = 'nutrition-v1'

    @model_validator(mode='after')
    def legacy_sugar_coverage(self):
        self.coverage.setdefault('sugar', 0)
        return self


class ConstraintResult(DataModel):
    constraint: str
    requested: float | str
    actual: float | str | None
    unit: str | None = None
    status: Literal['passed', 'failed', 'unknown']
    passed: bool | None
    difference: float | None = None
    reason: str
    evidence: list[str] = Field(default_factory=list)


class RecipeIntelligence(DataModel):
    calculated_nutrition: CalculatedNutrition
    nutrition_status: Literal['verified', 'partial', 'unavailable']
    nutrition_sources: list[IngredientNutrition]
    unmatched_ingredients: list[str]
    constraint_results: list[ConstraintResult] = Field(default_factory=list)
    overall_constraint_status: Literal['passed', 'failed', 'partially_verified'] = 'partially_verified'
    potential_allergen_warnings: list[str] = Field(default_factory=list)
    constraint_version: str = 'constraints-v1'
