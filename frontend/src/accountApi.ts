import { apiUrl } from './apiConfig';
import { supabase } from './supabase';
import { isSavedRecipe, SavedRecipe } from './recipeStorage';
import type { RecipeGenerationRequest } from './recipeApi';

export async function accountRequest<T>(path: string, method = 'GET', body?: unknown, expectedUserId?: string): Promise<T> {
  const session = supabase ? (await supabase.auth.getSession()).data.session : null;
  if (!session) throw new Error('Sign in to save recipes and access your account.');
  if (expectedUserId && session.user.id !== expectedUserId) throw new Error('Your account changed. Please try again.');
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 20000);
  let response: Response;
  try {
    response = await fetch(apiUrl(path), { method, signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session.access_token}` },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  } catch { throw new Error('MealMind backend is unavailable. Please try again.'); }
  finally { window.clearTimeout(timer); }
  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new Event('mealmind:auth-expired'));
      throw new Error('Your session expired. Please sign in again.');
    }
    if (response.status === 403) throw new Error('Permission denied for this account data.');
    if (response.status === 404) throw new Error(path.startsWith('/api/pantry') ? 'Pantry item no longer exists. Refresh your pantry.' : 'Saved recipe no longer exists.');
    const payload = await response.json().catch(() => null);
    if (payload?.error?.code === 'pantry_duplicate') throw new Error('This ingredient is already in your pantry. Edit the existing item instead.');
    if (payload?.error?.code === 'auth_not_configured') throw new Error('Account storage is not configured yet.');
    if (payload?.error?.code === 'supabase_unavailable') throw new Error('Supabase account storage is unavailable. Please try again.');
    throw new Error(response.status === 422 ? 'Please check your account data.' : 'MealMind could not complete this account request.');
  }
  return response.status === 204 ? undefined as T : response.json();
}
export interface SavedRow { id: string; source_id: string; recipe: SavedRecipe; created_at: string }
export type UserPreferences = {
  dietary_preferences: string[]; allergies: string[]; excluded_ingredients: string[];
  nutrition_targets: Partial<Pick<RecipeGenerationRequest, 'calorie_target' | 'protein_target' | 'carbs_target' | 'fat_target' | 'calorie_range' | 'carbs_range' | 'fat_range'>>;
  preferred_cuisines: string[];
  cooking_preferences: Partial<Pick<RecipeGenerationRequest, 'spice_level' | 'max_cooking_time' | 'difficulty' | 'servings' | 'meal_type'>>;
};
export const emptyPreferences: UserPreferences = { dietary_preferences: [], allergies: [], excluded_ingredients: [], nutrition_targets: {}, preferred_cuisines: [], cooking_preferences: {} };
export const listSaved = async () => {
  const rows = await accountRequest<SavedRow[]>('/api/saved-recipes');
  if (!Array.isArray(rows) || !rows.every(row => typeof row.id === 'string' && typeof row.source_id === 'string' && isSavedRecipe(row.recipe))) throw new Error('Account recipes could not be read. Your stored data was not changed.');
  return rows;
};
export const deleteSaved = (id: string, owner?: string) => accountRequest<void>(`/api/saved-recipes/${encodeURIComponent(id)}`, 'DELETE', undefined, owner);
export const createSaved = (recipe: Omit<SavedRecipe, 'savedAt'> & { savedAt?: string }, owner?: string) => accountRequest<SavedRow>('/api/saved-recipes', 'POST', {
  source_id: recipe.structuredRecipe?.recipe_version_id || recipe.id,
  recipe: { ...recipe, savedAt: recipe.savedAt || new Date().toISOString() },
}, owner);
export const getPreferences = () => accountRequest<UserPreferences>('/api/preferences');
export const putPreferences = (value: UserPreferences, owner?: string) => accountRequest<UserPreferences>('/api/preferences', 'PUT', value, owner);
