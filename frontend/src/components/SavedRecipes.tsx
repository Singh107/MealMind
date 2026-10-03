import { useAuth } from '../AuthContext';
import { useUserData } from '../UserDataContext';
import { importLegacy, pendingImports } from '../legacyImport';
import NutritionValue, { PartialNutritionNote } from './NutritionValue';
import { formatNutrient, GeneratedRecipe, nutritionLabel } from '../recipeApi';
import RecipeIntelligence from './RecipeIntelligence';
import React, { useState } from 'react';
import { readRecipes, writeRecipes, SavedRecipe } from '../recipeStorage';

export default function SavedRecipes({ onNavigate, onOpenRecipe }: { onNavigate: (section: string) => void; onOpenRecipe?: (recipe: GeneratedRecipe) => void }) {
  const auth = useAuth();
  const cloud = useUserData();
  const [busy, setBusy] = useState(false);
  const [importVersion, setImportVersion] = useState(0);
  const [initial] = useState(() => {
    try { return { recipes: readRecipes(), error: '' }; }
    catch { return { recipes: [] as SavedRecipe[], error: 'Your saved recipes could not be loaded. Check that browser storage is available, then reload.' }; }
  });
  const [localRecipes, setLocalRecipes] = useState(initial.recipes);
  const recipes = auth.signedIn ? cloud.recipes.map(row => ({ ...row.recipe, id: row.id })) : localRecipes;
  let importCount = 0;
  let importError = '';
  try { importCount = auth.user ? pendingImports(auth.user.id, localRecipes).length : 0; }
  catch (failure) { importError = (failure as Error).message; }

  const [error, setError] = useState(initial.error);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('date');
  const [selected, setSelected] = useState<string | null>(null);
  const filtered = recipes.filter(recipe => `${recipe.name} ${recipe.ingredients.join(' ')}`.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => sort === 'name' ? a.name.localeCompare(b.name) : b.savedAt.localeCompare(a.savedAt));
  const remove = async (id: string) => {
    try {
      if (auth.signedIn) await cloud.remove(id);
      else { const next = localRecipes.filter(recipe => recipe.id !== id); writeRecipes(next); setLocalRecipes(next); }
      setError('');
    } catch (failure) { setError(auth.signedIn ? (failure as Error).message : 'The recipe could not be removed. Check browser storage and try again.'); }
  };
  return <section className="mx-auto max-w-6xl px-4 py-8">
    <p className="text-sm font-semibold uppercase tracking-widest text-primary">Your collection</p>
    <h1 className="mt-2 text-3xl font-bold text-on-surface sm:text-4xl">Saved recipes</h1>
    <p className="mt-3 text-on-surface-variant">{auth.signedIn ? 'Your recipes, saved to your account.' : 'Local recipes from this device. Sign in to save new recipes to your account.'}</p>
    {(auth.loading || cloud.loading) && <p role="status">Loading your account...</p>}
    {!auth.signedIn && <button onClick={() => onNavigate('profile')} className="mt-3 text-primary">Sign In</button>}
    {cloud.error && <p role="alert">{cloud.error} <button onClick={() => void cloud.reload()}>Retry</button></p>}
    {importError && <p role="alert">{importError}</p>}
    {auth.user && importCount > 0 && <aside aria-label="Import local recipes" className="my-4 rounded-2xl border border-secondary/20 bg-secondary/5 p-5 space-y-3">
      <h2 className="font-semibold text-on-surface">{importCount} local {importCount === 1 ? 'recipe is' : 'recipes are'} ready to import</h2><p className="text-sm text-on-surface-variant break-words">Add them to your account ({auth.user.email}). Local copies will be kept.</p>
      <button className="mm-button mm-secondary min-h-[44px]" disabled={busy} onClick={async () => {
        setBusy(true); setError('');
        try { await importLegacy(auth.user!.id, localRecipes, cloud.save); }
        catch (failure) { setError((failure as Error).message); }
        finally { setBusy(false); setImportVersion(importVersion + 1); }
      }}>{busy ? 'Importing...' : 'Import local recipes'}</button>
    </aside>}
    {error && <p role="alert" className="mt-4 rounded-xl bg-error-container/20 p-4 text-error">{error}</p>}
    <div className="my-8 flex flex-col gap-4 sm:flex-row">
      <input aria-label="Search saved recipes" type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search recipes or ingredients" className="flex-1 rounded-xl border border-border px-4 py-3" />
      <select aria-label="Sort saved recipes" value={sort} onChange={event => setSort(event.target.value)} className="rounded-xl border border-border px-4 py-3"><option value="date">Newest first</option><option value="name">Name A–Z</option></select>
    </div>
    {filtered.length ? <div className="grid gap-5 lg:grid-cols-2">{filtered.map(recipe => <article key={recipe.id} className="rounded-2xl border border-border bg-surface-container p-6 shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-wider text-primary">{recipe.structuredRecipe ? 'Generated recipe' : 'Sample recipe'} · {recipe.difficulty}</p>
      <h2 className="mt-2 text-xl font-bold">{recipe.name}</h2>
      <p className="mt-3 text-sm text-on-surface-variant">{recipe.prepTime} prep · {recipe.cookTime} cooking · {recipe.servings} servings</p>
      <div className="mt-4 flex flex-wrap gap-2">{recipe.ingredients.slice(0, 5).map(ingredient => <span key={ingredient} className="rounded-full bg-surface-container-high px-3 py-1 text-sm text-on-surface-variant">{ingredient}</span>)}{recipe.ingredients.length > 5 && <span className="text-sm text-outline self-center">+{recipe.ingredients.length - 5} more</span>}</div>
      <div className="mt-6 flex flex-wrap gap-3">
        <button aria-expanded={selected === recipe.id} onClick={() => setSelected(selected === recipe.id ? null : recipe.id)} className="rounded-xl bg-primary-container px-4 py-3 text-sm font-semibold text-on-surface">{selected === recipe.id ? 'Hide details' : 'View details'}</button>
        <>{recipe.structuredRecipe && onOpenRecipe && <button onClick={() => onOpenRecipe(recipe.structuredRecipe!)} className="rounded-xl mm-action px-4 py-3 text-sm font-semibold">Open full recipe</button>}</>
        <button onClick={() => remove(recipe.id)} aria-label={`Remove ${recipe.name}`} className="rounded-xl px-4 py-3 text-sm font-semibold text-error">Remove</button>
      </div>
      {selected === recipe.id && <div className="mt-5 border-t border-border pt-5"><h3 className="font-semibold">All ingredients</h3><ul className="mb-4 list-disc pl-5 text-sm">{recipe.ingredients.map((ingredient, index) => <li key={index}>{ingredient}</li>)}</ul><h3 className="font-semibold">Instructions</h3><p className="mt-2 whitespace-pre-line leading-7 text-on-surface-variant">{recipe.instructions}</p><p className="mt-4 text-sm text-outline">{nutritionLabel(recipe.structuredRecipe)}: {recipe.structuredRecipe?.intelligence ? <NutritionValue recipe={recipe.structuredRecipe} nutrient="calories" /> : formatNutrient(recipe.nutrition.calories)} calories · {recipe.structuredRecipe?.intelligence ? <NutritionValue recipe={recipe.structuredRecipe} nutrient="protein" /> : formatNutrient(recipe.nutrition.protein, 'g')} protein</p>{recipe.structuredRecipe && <PartialNutritionNote recipe={recipe.structuredRecipe} />}{recipe.structuredRecipe && <RecipeIntelligence recipe={recipe.structuredRecipe} />}</div>}
    </article>)}</div> : <div className="rounded-2xl border border-dashed border-border bg-surface-container-low p-10 text-center">
      <h2 className="text-xl font-semibold">{recipes.length ? 'No matching recipes' : 'Your next favorite starts here'}</h2>
      <p className="mt-2 text-on-surface-variant">{recipes.length ? 'Try another recipe name or ingredient.' : 'Create a recipe and save it to build your collection.'}</p>
      <button onClick={() => recipes.length ? setSearch('') : onNavigate('generator')} className="mt-6 rounded-xl bg-primary-container px-5 py-3 font-semibold text-on-surface">{recipes.length ? 'Clear search' : 'Create a recipe'}</button>
    </div>}
  </section>;
}
