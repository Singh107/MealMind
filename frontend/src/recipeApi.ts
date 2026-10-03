import { isRepairResponse } from './repairApi';
import type { SavedRecipe } from './recipeStorage';
import { apiUrl } from './apiConfig';
import { isRecipeIntelligence, NutrientValues, RecipeIntelligence } from './nutritionTypes';

export interface RecipeGenerationRequest {
  selected_ingredients: string[];
  calorie_target: number | null;
  protein_target: number | null;
  carbs_target: number | null;
  fat_target: number | null;
  cuisine: string | null;
  spice_level: string | null;
  max_cooking_time: number | null;
  difficulty: string | null;
  servings: number;
  dietary_preferences: string[];
  allergies: string[];
  excluded_ingredients: string[];
  meal_type: string | null;
  calorie_range?: { minimum?: number | null; maximum?: number | null } | null;
  carbs_range?: { minimum?: number | null; maximum?: number | null } | null;
  fat_range?: { minimum?: number | null; maximum?: number | null } | null;
}

export interface GeneratedRecipe {
  id: string;
  recipe_version_id: string;
  title: string;
  description: string;
  ingredients: { name: string; quantity: number; unit: string }[];
  instructions: string[];
  prep_time: number;
  cook_time: number;
  total_time: number;
  servings: number;
  cuisine: string;
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  dietary_tags: string[];
  potential_allergens: string[];
  nutrition: { calories: number | null; protein: number | null; carbohydrates: number | null;
    fat: number | null; fiber: number | null; sodium: number | null };
  validation_status: 'unverified';
  nutrition_source: 'ai_estimate';
  nutrition_basis: 'per_serving';
  // Attached from the additive response for navigation and local saves.
  intelligence?: RecipeIntelligence;
  original_request?: RecipeGenerationRequest;
  optimization?: import('./repairApi').RepairResponse;
  substitution?: { original_recipe: GeneratedRecipe; before_intelligence: RecipeIntelligence; change: import('./substitutionApi').SubstitutionPreview['change']; message: string };
}

export interface RecipeGenerationResponse extends Partial<RecipeIntelligence> {
  evaluated_request?: RecipeGenerationRequest;
  recipe: GeneratedRecipe;
  warnings: string[];
  metadata: { provider: string; model: string; prompt_version: string; schema_version: string };
  trace_id: string;
}

const record = (value: unknown): value is Record<string, any> => !!value && typeof value === 'object' && !Array.isArray(value);
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(nonempty);
const numeric = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;
export function isGeneratedRecipe(value: unknown): value is GeneratedRecipe {
  if (!record(value)) return false;
  return ['id', 'recipe_version_id', 'title', 'description', 'cuisine'].every(key => nonempty(value[key])) &&
    ['prep_time', 'cook_time', 'total_time', 'servings'].every(key => numeric(value[key]) && Number.isInteger(value[key])) &&
    value.servings >= 1 && value.servings <= 12 && value.total_time > 0 && value.total_time === value.prep_time + value.cook_time &&
    ['beginner', 'intermediate', 'advanced'].includes(value.difficulty) &&
    strings(value.instructions) && value.instructions.length > 0 && strings(value.dietary_tags) && strings(value.potential_allergens) &&
    Array.isArray(value.ingredients) && value.ingredients.length > 0 && value.ingredients.every((item: unknown) =>
      record(item) && nonempty(item.name) && nonempty(item.unit) && numeric(item.quantity) && item.quantity > 0) &&
    record(value.nutrition) && ['calories', 'protein', 'carbohydrates', 'fat', 'fiber', 'sodium'].every(key =>
      value.nutrition[key] === null || numeric(value.nutrition[key])) &&
    value.validation_status === 'unverified' && value.nutrition_source === 'ai_estimate' && value.nutrition_basis === 'per_serving' &&
    (value.optimization === undefined || isRepairResponse(value.optimization)) &&
    (value.substitution === undefined || (record(value.substitution) && value.substitution.original_recipe?.substitution === undefined && isGeneratedRecipe(value.substitution.original_recipe) && isRecipeIntelligence(value.substitution.before_intelligence) && typeof value.substitution.message === 'string' && record(value.substitution.change))) &&
    (value.intelligence === undefined || (isRecipeIntelligence(value.intelligence) && value.intelligence.calculated_nutrition.servings === value.servings));
}

export function parseGenerationResponse(value: unknown): RecipeGenerationResponse {
  if (!record(value) || !isGeneratedRecipe(value.recipe) || !strings(value.warnings) ||
    !nonempty(value.trace_id) || !record(value.metadata) ||
    !['provider', 'model', 'prompt_version', 'schema_version'].every(key => nonempty(value.metadata[key]))) {
    throw new Error('The server returned an invalid recipe. Please try again.');
  }
  if (value.calculated_nutrition !== undefined || value.metadata.schema_version === '1.1') {
    const response = value as unknown as RecipeGenerationResponse;
    if (!isRecipeIntelligence(value) || value.calculated_nutrition.servings !== response.recipe.servings ||
      value.calculated_nutrition.ingredient_count !== response.recipe.ingredients.length) {
      throw new Error('The server returned invalid nutrition verification. Please try again.');
    }
    const { calculated_nutrition, nutrition_status, nutrition_sources, unmatched_ingredients,
      constraint_results, overall_constraint_status, potential_allergen_warnings, constraint_version } = value;
    return { ...response, recipe: { ...response.recipe, intelligence: { calculated_nutrition, nutrition_status, nutrition_sources,
      unmatched_ingredients, constraint_results, overall_constraint_status, potential_allergen_warnings, constraint_version } } } as RecipeGenerationResponse;
  }
  return value as unknown as RecipeGenerationResponse;
}

export async function generateRecipe(request: RecipeGenerationRequest, signal: AbortSignal, accessToken?: string | null): Promise<RecipeGenerationResponse> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) controller.abort();
  let timedOut = false;
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 50000);
  try {
    await checkBackendHealth(controller.signal);
    if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const response = await fetch(apiUrl('/api/recipes/generate'), {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) }, body: JSON.stringify(request), signal: controller.signal,
    });
    let payload: unknown;
    try { payload = await response.json(); }
    catch {
      if (response.ok) throw new Error('The server returned an unreadable response. Please try again.');
      payload = null;
    }
    if (!response.ok) {
      const code = record(payload) && record(payload.error) ? payload.error.code : '';
      if (code === 'invalid_request' || response.status === 422) throw new Error('Some recipe preferences are invalid. Please review them.');
      if (code === 'provider_timeout' || response.status === 504) throw new Error('Recipe generation took too long. Please try again.');
      throw new Error('The recipe AI is temporarily unavailable. Please try again.');
    }
    const parsed = parseGenerationResponse(payload);
    return { ...parsed, recipe: { ...parsed.recipe, original_request: parsed.evaluated_request || request } };
  } catch (error) {
    if (timedOut) throw new Error('Recipe generation took too long. Please try again.');
    if (error instanceof TypeError) throw new Error('MealMind cannot reach the local server. Make sure the backend is running.');
    throw error;
  } finally {
    clearTimeout(timeout);
    signal.removeEventListener('abort', abort);
  }
}

export async function checkBackendHealth(signal: AbortSignal): Promise<void> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) controller.abort();
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 5000);
  try {
    const response = await fetch(apiUrl('/health'), { signal: controller.signal, cache: 'no-store' });
    if (!response.ok) throw new Error('MealMind cannot reach a healthy local server. Make sure the backend is running.');
  } catch (error) {
    if (timedOut) throw new Error('The local server took too long to respond. Please try again.');
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
  }
}

export function toSavedRecipe(recipe: GeneratedRecipe): Omit<SavedRecipe, 'savedAt'> {
  const nutrition = displayNutrition(recipe);
  return {
    id: recipe.id, name: recipe.title,
    ingredients: recipe.ingredients.map(item => `${item.quantity} ${item.unit} ${item.name}`),
    instructions: recipe.instructions.map((step, i) => `${i + 1}. ${step}`).join('\n'),
    prepTime: `${recipe.prep_time} mins`, cookTime: `${recipe.cook_time} mins`,
    servings: recipe.servings, difficulty: recipe.difficulty,
    nutrition: { calories: nutrition.calories, protein: nutrition.protein,
      carbs: nutrition.carbohydrates, fat: nutrition.fat },
    structuredRecipe: recipe,
  };
}

export const formatNutrient = (value: number | null, unit = '') => value === null ? 'Unknown' : `${value}${unit}`;

export const displayNutrition = (recipe: GeneratedRecipe): NutrientValues => recipe.intelligence?.calculated_nutrition.per_serving || recipe.nutrition;
export const nutritionLabel = (recipe?: GeneratedRecipe) => !recipe ? 'Sample nutrition' : !recipe.intelligence
  ? 'AI nutrition estimate (unverified)' : recipe.intelligence.nutrition_status === 'verified'
  ? 'Nutrition calculated from USDA food data' : recipe.intelligence.nutrition_status === 'partial'
  ? 'Nutrition partially calculated' : 'Calculated nutrition unavailable';



// Presentation only. Never replace complete totals used by constraints, repair, or storage.
export function formatCalculatedNutrient(recipe: GeneratedRecipe, nutrient: keyof NutrientValues): string {
  const report = recipe.intelligence;
  if (!report) return 'Unknown';
  const complete = report.calculated_nutrition.per_serving[nutrient];
  const known = report.calculated_nutrition.known_per_serving[nutrient];
  const unit = nutrient === 'calories' ? 'kcal' : nutrient === 'sodium' ? 'mg' : 'g';
  const format = (value: number) => `${value > 0 && value < 0.005 ? '<0.01' : Math.round(value * 100) / 100} ${unit}`;
  if (complete != null) return format(complete);
  if (known != null && known > 0) return format(known);
  return 'Unknown';
}


export function isPartialNutrient(recipe: GeneratedRecipe, nutrient: keyof NutrientValues): boolean {
  const n = recipe.intelligence?.calculated_nutrition;
  return !!n && n.per_serving[nutrient] == null && (n.known_per_serving[nutrient] ?? 0) > 0;
}
