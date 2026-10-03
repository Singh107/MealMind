import { SavedRecipe } from './recipeStorage';

const key = (userId: string) => `mealmind.importedRecipes.v1.${userId}`;
export function pendingImports(userId: string, recipes: SavedRecipe[]): SavedRecipe[] {
  const raw: unknown = JSON.parse(localStorage.getItem(key(userId)) || '[]');
  if (!Array.isArray(raw) || !raw.every(value => typeof value === 'string')) throw new Error('The local import record could not be read. Local recipes were retained.');
  return recipes.filter(recipe => !raw.includes(recipe.id));
}
export async function importLegacy(userId: string, recipes: SavedRecipe[], save: (recipe: SavedRecipe) => Promise<void>) {
  for (const recipe of pendingImports(userId, recipes)) {
    await save(recipe);
    const completed: string[] = JSON.parse(localStorage.getItem(key(userId)) || '[]');
    localStorage.setItem(key(userId), JSON.stringify([...completed, recipe.id]));
  }
  // Keep original local recipes. Server uniqueness also handles a lost response/marker write.
}
