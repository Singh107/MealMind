import React from 'react';
import { GeneratedRecipe, formatCalculatedNutrient, isPartialNutrient } from '../recipeApi';
import { NutrientValues } from '../nutritionTypes';

export default function NutritionValue({ recipe, nutrient }: {
  recipe: GeneratedRecipe; nutrient: keyof NutrientValues;
}) {
  return <span>
    <span>{formatCalculatedNutrient(recipe, nutrient)}</span>
    {isPartialNutrient(recipe, nutrient) && <span className="block text-xs font-normal text-outline">Partial data</span>}
  </span>;
}

export function PartialNutritionNote({ recipe }: { recipe: GeneratedRecipe }) {
  const n = recipe.intelligence?.calculated_nutrition;
  const incomplete = recipe.intelligence?.nutrition_status === 'partial' || (!!n &&
    Object.keys(n.per_serving).some(k => n.per_serving[k as keyof NutrientValues] == null &&
      n.known_per_serving[k as keyof NutrientValues] != null));
  return incomplete ? <p className="my-3 text-sm font-normal text-on-surface-variant">
    Nutrition uses available USDA data. Some ingredients or nutrients are missing, so totals may be incomplete.
  </p> : null;
}
