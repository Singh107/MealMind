import { accountRequest } from './accountApi';
import type { GeneratedRecipe } from './recipeApi';

export interface PantryInput { name: string; quantity: number | null; unit: string | null }
export interface PantryItem extends PantryInput {
  id: string; normalized_name: string; food_state: string | null;
  identity_status: 'recognized' | 'unresolved'; created_at: string; updated_at: string;
}
export interface PantryCompatibility {
  pantry_count: number; usable_pantry_count: number; ingredient_count: number; available_count: number;
  missing_count: number; unknown_count: number; coverage_percent: number | null; basis: string;
  ingredients: { ingredient_index: number; name: string; status: 'available' | 'missing' | 'unknown'; reason: string; pantry_item_id: string | null; quantity_status?: 'sufficient' | 'insufficient' | 'unknown'; quantity_reason?: string }[];
}
export const listPantry = (owner: string) => accountRequest<PantryItem[]>('/api/pantry', 'GET', undefined, owner);
export const savePantry = (owner: string, item: PantryInput, id?: string) => accountRequest<PantryItem>(
  id ? `/api/pantry/${encodeURIComponent(id)}` : '/api/pantry', id ? 'PUT' : 'POST', item, owner);
export const deletePantry = (owner: string, id: string) => accountRequest<void>(`/api/pantry/${encodeURIComponent(id)}`, 'DELETE', undefined, owner);
export const pantryCompatibility = (owner: string, ingredients: GeneratedRecipe['ingredients']) =>
  accountRequest<PantryCompatibility>('/api/pantry/compatibility', 'POST', { ingredients }, owner);
