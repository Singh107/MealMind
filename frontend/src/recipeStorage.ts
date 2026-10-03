import { GeneratedRecipe, isGeneratedRecipe } from './recipeApi';

export interface SavedRecipe {
  id: string;
  name: string;
  ingredients: string[];
  instructions: string;
  prepTime: string;
  cookTime: string;
  servings: number;
  difficulty: string;
  nutrition: { calories: number | null; protein: number | null; carbs: number | null; fat: number | null };
  structuredRecipe?: GeneratedRecipe;
  savedAt: string;
}
const storageKey = 'mealmind.savedRecipes.v1';
export function readRecipes(): SavedRecipe[] {
  const raw = localStorage.getItem(storageKey);
  if (!raw) return [];
  const recipes: unknown = JSON.parse(raw);
  if (!Array.isArray(recipes) || !recipes.every(isSavedRecipe)) throw new Error('Saved recipe data could not be read.');
  return recipes;
}
export function isSavedRecipe(recipe: any): recipe is SavedRecipe {
  return !!(recipe && typeof recipe.id === 'string' && typeof recipe.name === 'string' &&
    Array.isArray(recipe.ingredients) && recipe.ingredients.every((item: unknown) => typeof item === 'string') &&
    typeof recipe.instructions === 'string' && typeof recipe.savedAt === 'string' &&
    typeof recipe.servings === 'number' && typeof recipe.prepTime === 'string' &&
    typeof recipe.cookTime === 'string' && typeof recipe.difficulty === 'string' &&
    recipe.nutrition && ['calories', 'protein', 'carbs', 'fat'].every(key => recipe.nutrition[key] === null || (typeof recipe.nutrition[key] === 'number' && Number.isFinite(recipe.nutrition[key]))) &&
    (recipe.structuredRecipe === undefined || isGeneratedRecipe(recipe.structuredRecipe))
  );
}
export function writeRecipes(recipes: SavedRecipe[]) {
  localStorage.setItem(storageKey, JSON.stringify(recipes));
}
export function saveRecipe(recipe: Omit<SavedRecipe, 'id' | 'savedAt'> & { id?: string }) {
  const recipes = readRecipes();
  const id = recipe.id || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  if (recipes.some(existing => existing.id === id)) return;
  writeRecipes([{ ...recipe, id, savedAt: new Date().toISOString() }, ...recipes]);
}
