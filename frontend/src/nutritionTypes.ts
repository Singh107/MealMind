export interface NutrientValues {
  calories: number | null;
  protein: number | null;
  carbohydrates: number | null;
  fat: number | null;
  fiber: number | null;
  sodium: number | null;
  sugar?: number | null;
}

export interface ConstraintResult {
  constraint: string;
  requested: number | string;
  actual: number | string | null;
  unit: string | null;
  status: 'passed' | 'failed' | 'unknown';
  passed: boolean | null;
  difference: number | null;
  reason: string;
  evidence: string[];
}

export interface RecipeIntelligence {
  calculated_nutrition: {
    totals: NutrientValues;
    per_serving: NutrientValues;
    known_totals: NutrientValues;
    known_per_serving: NutrientValues;
    coverage: Record<Exclude<keyof NutrientValues, 'sugar'>, number> & { sugar?: number };
    ingredient_count: number;
    servings: number;
    calculation_version: string;
  };
  nutrition_status: 'verified' | 'partial' | 'unavailable';
  nutrition_sources: {
    ingredient_index: number;
    ingredient: { original_text: string; name: string; grams: number | null; food_state: string | null;
      preparation: string | null; conversion_evidence: string | null };
    status: 'calculated' | 'partial' | 'unmatched' | 'unavailable' | 'unconvertible';
    reason: string | null;
    food: { source: 'usda_fdc'; food_id: string; description: string; retrieved_at: string;
      match_quality: string; nutrients_per_100g: NutrientValues } | null;
  }[];
  unmatched_ingredients: string[];
  constraint_results: ConstraintResult[];
  overall_constraint_status: 'passed' | 'failed' | 'partially_verified';
  potential_allergen_warnings: string[];
  constraint_version: string;
}

const object = (v: unknown): v is Record<string, any> => v !== null && typeof v === 'object' && !Array.isArray(v);
const texts = (v: unknown): v is string[] => Array.isArray(v) && v.every(x => typeof x === 'string');
const number = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0;
const nullableText = (v: unknown) => v === null || typeof v === 'string';
const keys: (keyof NutrientValues)[] = ['calories', 'protein', 'carbohydrates', 'fat', 'fiber', 'sodium'];
const nutrients = (v: unknown) => object(v) && keys.every(key => v[key] === null || number(v[key])) && (v.sugar === undefined || v.sugar === null || number(v.sugar));

export function isRecipeIntelligence(v: unknown): v is RecipeIntelligence {
  if (!object(v) || !object(v.calculated_nutrition)) return false;
  const n = v.calculated_nutrition;
  if (!['verified', 'partial', 'unavailable'].includes(v.nutrition_status) ||
    !['passed', 'failed', 'partially_verified'].includes(v.overall_constraint_status) ||
    ![n.totals, n.per_serving, n.known_totals, n.known_per_serving].every(nutrients) ||
    !number(n.ingredient_count) || !Number.isInteger(n.ingredient_count) ||
    !number(n.servings) || n.servings < 1 || !Number.isInteger(n.servings) ||
    !object(n.coverage) || !keys.every(key => number(n.coverage[key]) && Number.isInteger(n.coverage[key]) && n.coverage[key] <= n.ingredient_count) ||
    typeof n.calculation_version !== 'string' || typeof v.constraint_version !== 'string' ||
    !texts(v.unmatched_ingredients) || !texts(v.potential_allergen_warnings) || !Array.isArray(v.constraint_results) ||
    !v.constraint_results.every((r: unknown) => object(r) && typeof r.constraint === 'string' &&
      (typeof r.requested === 'string' || number(r.requested)) &&
      (r.actual === null || typeof r.actual === 'string' || number(r.actual)) &&
      ['passed', 'failed', 'unknown'].includes(r.status) && r.passed === ({ passed: true, failed: false, unknown: null } as Record<string, boolean | null>)[r.status] &&
      (r.difference === null || (typeof r.difference === 'number' && Number.isFinite(r.difference))) &&
      typeof r.reason === 'string' && nullableText(r.unit) && texts(r.evidence)) ||
    !Array.isArray(v.nutrition_sources) || v.nutrition_sources.length !== n.ingredient_count ||
    !v.nutrition_sources.every((r: unknown) => object(r) && number(r.ingredient_index) && object(r.ingredient) &&
      typeof r.ingredient.original_text === 'string' && typeof r.ingredient.name === 'string' &&
      (r.ingredient.grams === null || number(r.ingredient.grams)) && nullableText(r.ingredient.food_state) &&
      nullableText(r.ingredient.preparation) && nullableText(r.ingredient.conversion_evidence) &&
      ['calculated', 'partial', 'unmatched', 'unavailable', 'unconvertible'].includes(r.status) && nullableText(r.reason) &&
      (r.food === null || (object(r.food) && r.food.source === 'usda_fdc' && typeof r.food.food_id === 'string' &&
      /^\d+$/.test(r.food.food_id) && typeof r.food.description === 'string' && typeof r.food.retrieved_at === 'string' &&
      typeof r.food.match_quality === 'string' && nutrients(r.food.nutrients_per_100g))))) return false;
  return v.nutrition_status !== 'verified' || (n.ingredient_count > 0 &&
    ['calories', 'protein', 'carbohydrates', 'fat'].every(key => number(n.totals[key]) && number(n.per_serving[key]) && n.coverage[key] === n.ingredient_count));
}
