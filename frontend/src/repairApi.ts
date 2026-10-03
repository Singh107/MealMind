import { apiUrl } from './apiConfig';
import { GeneratedRecipe, isGeneratedRecipe } from './recipeApi';
import { RecipeIntelligence, isRecipeIntelligence } from './nutritionTypes';

export interface RepairResponse {
  repair_status: 'not_needed' | 'repaired' | 'partially_repaired' | 'failed';
  repair_attempts: number;
  original_recipe: GeneratedRecipe;
  final_recipe: GeneratedRecipe;
  before_intelligence: RecipeIntelligence;
  after_intelligence: RecipeIntelligence;
  changes: { ingredient: string; before: string; after: string; reason: string }[];
  remaining_failed_constraints: RecipeIntelligence['constraint_results'];
  message: string;
  failure_code: string | null;
  trace_id: string;
}

export function isRepairResponse(value: any): value is RepairResponse {
  return !!value && ['not_needed', 'repaired', 'partially_repaired', 'failed'].includes(value.repair_status) &&
    Number.isInteger(value.repair_attempts) && value.repair_attempts >= 0 && value.repair_attempts <= 2 &&
    value.original_recipe?.optimization === undefined && value.final_recipe?.optimization === undefined &&
    isGeneratedRecipe(value.original_recipe) && isGeneratedRecipe(value.final_recipe) &&
    isRecipeIntelligence(value.before_intelligence) && isRecipeIntelligence(value.after_intelligence) &&
    value.before_intelligence.calculated_nutrition.servings === value.original_recipe.servings &&
    value.after_intelligence.calculated_nutrition.servings === value.final_recipe.servings &&
    Array.isArray(value.changes) && value.changes.every((c: any) => c &&
      ['ingredient', 'before', 'after', 'reason'].every(k => typeof c[k] === 'string')) &&
    Array.isArray(value.remaining_failed_constraints) && value.remaining_failed_constraints.every((r: any) => r && typeof r.constraint === 'string' && r.status === 'failed') && typeof value.message === 'string' && typeof value.trace_id === 'string';
}

export async function repairRecipe(recipe: GeneratedRecipe, signal: AbortSignal): Promise<RepairResponse> {
  if (!recipe.original_request) throw new Error('Original preferences are unavailable. Generate a new recipe to optimize it.');
  const { id, recipe_version_id, validation_status, nutrition_source, nutrition_basis,
    intelligence, optimization, substitution, original_request, ...candidate } = recipe;
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) controller.abort();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 125000);
  try {
    const response = await fetch(apiUrl('/api/recipes/repair'), { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recipe: candidate, constraints: original_request }), signal: controller.signal });
    if (!response.ok) throw new Error(response.status === 422 ? 'Some recipe preferences are invalid. Please review them.' :
      'The recipe AI is temporarily unavailable. Please try again.');
    const data: unknown = await response.json();
    if (!isRepairResponse(data)) throw new Error('The server returned an invalid optimization. Your recipe is unchanged.');
    return data;
  } catch (error) {
    if (timedOut) throw new Error('Recipe optimization took too long. Your recipe is unchanged.');
    if (error instanceof TypeError) throw new Error('MealMind cannot reach the local server. Make sure the backend is running.');
    throw error;
  } finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
}
