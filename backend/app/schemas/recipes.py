from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from app.schemas.intelligence import RecipeIntelligence

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Nutrient = Annotated[float, Field(ge=0, le=100000, allow_inf_nan=False)]
Names = Annotated[list[Name], Field(max_length=50)]
Difficulty = Literal['beginner', 'intermediate', 'advanced']
Diet = Literal['vegetarian', 'vegan', 'pescatarian', 'gluten-free', 'dairy-free',
               'nut-free', 'low-carb', 'high-protein', 'keto']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class NutrientRange(Contract):
    minimum: Annotated[float, Field(ge=0, le=2000)] | None = None
    maximum: Annotated[float, Field(ge=0, le=2000)] | None = None

    @model_validator(mode='after')
    def check_bounds(self):
        if self.minimum is None and self.maximum is None:
            raise ValueError('A range needs at least one bound.')
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError('Minimum must not exceed maximum.')
        return self


class RecipeGenerationRequest(Contract):
    selected_ingredients: Annotated[list[Name], Field(min_length=1, max_length=50)]
    calorie_target: Annotated[float, Field(ge=0, le=2000)] | None = None
    protein_target: Annotated[float, Field(ge=0, le=200)] | None = None
    carbs_target: Annotated[float, Field(ge=0, le=300)] | None = None
    fat_target: Annotated[float, Field(ge=0, le=100)] | None = None
    calorie_range: NutrientRange | None = None
    carbs_range: NutrientRange | None = None
    fat_range: NutrientRange | None = None
    cuisine: Name | None = None
    spice_level: Literal['mild', 'medium', 'spicy', 'very-spicy'] | None = None
    max_cooking_time: Annotated[int, Field(ge=1, le=1440)] | None = None
    difficulty: Difficulty | None = None
    servings: Annotated[int, Field(ge=1, le=12)] = 4
    dietary_preferences: Annotated[list[Diet], Field(max_length=9)] = Field(default_factory=list)
    allergies: Names = Field(default_factory=list)
    excluded_ingredients: Names = Field(default_factory=list)
    meal_type: Literal['breakfast', 'lunch', 'dinner', 'snack', 'dessert'] | None = None

    @model_validator(mode='after')
    def reject_explicit_conflict(self):
        for target, bounds in [(self.calorie_target, self.calorie_range), (self.carbs_target, self.carbs_range), (self.fat_target, self.fat_range)]:
            if target is not None and bounds is not None:
                raise ValueError('Choose either a maximum target or a range for each nutrient, not both.')
        # Direct name conflicts only; this is not an allergen/constraint engine.
        excluded = {name.casefold() for name in self.excluded_ingredients + self.allergies}
        if any(name.casefold() in excluded for name in self.selected_ingredients):
            raise ValueError('A selected ingredient is also explicitly excluded or listed as an allergy.')
        return self


class RecipeIngredient(Contract):
    name: Name
    quantity: Annotated[float, Field(gt=0, le=100000, allow_inf_nan=False)]
    unit: Name


class NutritionInfo(Contract):
    """Per serving estimates: kcal, grams of macros/fiber, milligrams of sodium."""
    calories: Nutrient | None
    protein: Nutrient | None
    carbohydrates: Nutrient | None
    fat: Nutrient | None
    fiber: Nutrient | None = None
    sodium: Nutrient | None = None


class RecipeCandidate(Contract):
    """Only content is model-authored; provenance/status/IDs are server-owned."""
    title: Name
    description: Text
    ingredients: Annotated[list[RecipeIngredient], Field(min_length=1, max_length=50)]
    instructions: Annotated[list[Text], Field(min_length=1, max_length=40)]
    prep_time: Annotated[int, Field(ge=0, le=1440)]
    cook_time: Annotated[int, Field(ge=0, le=1440)]
    total_time: Annotated[int, Field(ge=1, le=2880)]
    servings: Annotated[int, Field(ge=1, le=12)]
    cuisine: Name
    difficulty: Difficulty
    dietary_tags: Names
    potential_allergens: Names
    nutrition: NutritionInfo

    @model_validator(mode='after')
    def check_times(self):
        if self.total_time != self.prep_time + self.cook_time:
            raise ValueError('Total time must equal prep time plus cook time.')
        return self


class GeneratedRecipe(RecipeCandidate):
    id: UUID
    recipe_version_id: UUID
    validation_status: Literal['unverified'] = 'unverified'
    nutrition_source: Literal['ai_estimate'] = 'ai_estimate'
    nutrition_basis: Literal['per_serving'] = 'per_serving'


class GenerationMetadata(Contract):
    provider: str
    model: str
    prompt_version: str = 'recipe-v1'
    schema_version: str = '1.1'


class RecipeGenerationResponse(RecipeIntelligence, Contract):
    evaluated_request: RecipeGenerationRequest | None = None
    recipe: GeneratedRecipe
    warnings: list[str]
    metadata: GenerationMetadata
    trace_id: str
