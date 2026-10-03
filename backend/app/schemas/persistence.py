"""Stored snapshots are user data, not newly verified nutrition assertions."""
import json
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.recipes import RecipeGenerationRequest

class SavedRecipeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str = Field(min_length=1, max_length=160, pattern=r'^[a-zA-Z0-9._:-]+$')
    recipe: dict[str, Any]

    @model_validator(mode='after')
    def snapshot(self):
        if len(json.dumps(self.recipe, allow_nan=False).encode()) > 2_000_000:
            raise ValueError('Recipe snapshot is too large.')
        for key in ['name', 'instructions', 'prepTime', 'cookTime', 'difficulty', 'savedAt']:
            if not isinstance(self.recipe.get(key), str):
                raise ValueError('Invalid saved recipe snapshot.')
        if not isinstance(self.recipe.get('ingredients'), list) or not all(isinstance(i, str) for i in self.recipe['ingredients']):
            raise ValueError('Invalid saved ingredients.')
        if not isinstance(self.recipe.get('nutrition'), dict) or not isinstance(self.recipe.get('servings'), int):
            raise ValueError('Invalid saved nutrition or servings.')
        return self

class PreferencesInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Reuse generation semantics, excluding the current ingredient selection.
    dietary_preferences: list[str] = Field(default_factory=list, max_length=9)
    allergies: list[str] = Field(default_factory=list, max_length=50)
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=50)
    nutrition_targets: dict[str, Any] = Field(default_factory=dict)
    preferred_cuisines: list[str] = Field(default_factory=list, max_length=20)
    cooking_preferences: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def compatible(self):
        if set(self.nutrition_targets) - {'calorie_target', 'protein_target', 'carbs_target', 'fat_target', 'calorie_range', 'carbs_range', 'fat_range'}:
            raise ValueError('Unknown nutrition target.')
        if set(self.cooking_preferences) - {'spice_level', 'max_cooking_time', 'difficulty', 'servings', 'meal_type'}:
            raise ValueError('Unknown cooking preference.')
        # Use a neutral selected ingredient solely to validate the existing request contract.
        request = dict(selected_ingredients=['preference validation'], dietary_preferences=self.dietary_preferences,
            allergies=self.allergies, excluded_ingredients=self.excluded_ingredients,
            **self.nutrition_targets, **self.cooking_preferences)
        RecipeGenerationRequest.model_validate(request)
        if any(not c.strip() or len(c) > 120 for c in self.preferred_cuisines):
            raise ValueError('Invalid cuisine.')
        return self

class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    display_name: str = Field(default='', max_length=120)
