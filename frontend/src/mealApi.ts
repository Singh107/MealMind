import { apiUrl } from './apiConfig';
import { requestImage, Detection } from './visionApi';
import { isRecipeIntelligence, RecipeIntelligence } from './nutritionTypes';

export interface MealProposal { analysis_id: string; meal_name: string | null; components: Omit<Detection, 'merged_count'>[]; limitations: string[] }
export interface MealNutrition { analysis_id: string; basis: 'entered_consumed_amounts'; nutrition: RecipeIntelligence }
export interface MealAmount { name: string; quantity: number; unit: string }

export const analyzeMeal = (file: File, signal: AbortSignal): Promise<MealProposal> => requestImage(file, signal, '/api/vision/meal', value =>
  !!value && typeof value.analysis_id === 'string' && (value.meal_name === null || typeof value.meal_name === 'string') &&
  Array.isArray(value.components) && value.components.length <= 30 && value.components.every((c: any) =>
    typeof c.display_name === 'string' && c.display_name.trim().length > 0 && c.display_name.length <= 120 &&
    ['high','medium','low'].includes(c.confidence) && typeof c.uncertainty === 'string' &&
    [null,'raw','cooked','dry','canned','fried','roasted','steamed','boiled','baked'].includes(c.visible_state) &&
    ['recognized','unresolved','conflicting'].includes(c.identity_status) && typeof c.normalized_name === 'string'));

export async function calculateMeal(components: MealAmount[], signal: AbortSignal): Promise<MealNutrition> {
  const controller = new AbortController(); const abort = () => controller.abort();
  signal.addEventListener('abort', abort); if (signal.aborted) abort();
  const timer = window.setTimeout(abort, 25000);
  try {
    const response = await fetch(apiUrl('/api/nutrition/meal'), { method: 'POST', signal: controller.signal,
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({confirmed: true, components}) });
    if (!response.ok) throw new Error('Meal nutrition could not be calculated. Check your entries and try again.');
    const value = await response.json();
    if (!value || typeof value.analysis_id !== 'string' || value.basis !== 'entered_consumed_amounts' || !isRecipeIntelligence(value.nutrition)) throw new Error('Meal nutrition could not be read.');
    return value;
  } finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
}
