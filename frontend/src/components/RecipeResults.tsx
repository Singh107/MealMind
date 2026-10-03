import React, { useState, useEffect } from 'react';
import { GeneratedRecipe, toSavedRecipe, nutritionLabel } from '../recipeApi';
import { useUserData } from '../UserDataContext';
import NutritionValue, { PartialNutritionNote } from './NutritionValue';
import RecipeOptimization from './RecipeOptimization';
import RecipeIntelligence from './RecipeIntelligence';
import { Icon } from './DesignShell';
interface Props { onNavigate: (section: string) => void; generatedRecipe?: GeneratedRecipe | null; onRecipeUpdated?: (recipe: GeneratedRecipe) => void; onOpenRecipe?: (recipe: GeneratedRecipe) => void }
export default function RecipeResults({ onNavigate, generatedRecipe: initial, onRecipeUpdated, onOpenRecipe }: Props) {
  const [recipe, setRecipe] = useState(initial); const [error,setError] = useState(''); const [busy,setBusy] = useState(false);
  const cloud = useUserData();
  useEffect(() => { setRecipe(initial); }, [initial]);
  const saved = cloud.recipes.find(row => row.source_id === recipe?.recipe_version_id);
  const update = (next: GeneratedRecipe) => { setRecipe(next); onRecipeUpdated?.(next); };
  return <section className="mm-page space-y-5"><p className="mm-kicker">From your ingredients</p><h1 className="font-bold">Your Generated Recipes</h1>
    {!recipe ? <div className="mm-panel space-y-4"><p>No generated recipe yet. Start with your ingredients.</p><button className="mm-button" onClick={() => onNavigate('generator')}>Create a recipe</button></div> : <article className="mm-panel space-y-4">
      <div className="flex justify-between gap-3"><span className="text-sm text-on-surface-variant">{recipe.cuisine} / {recipe.total_time} min · {recipe.servings} servings</span><Icon>soup_kitchen</Icon></div>
      <h2 className="text-2xl font-bold">{recipe.title}</h2><p className="text-on-surface-variant">{recipe.description}</p>
      <p className="text-sm text-on-surface-variant">{nutritionLabel(recipe)}</p><div className="flex flex-wrap gap-6"><div>Calories <NutritionValue recipe={recipe} nutrient="calories" /></div><div>Protein <NutritionValue recipe={recipe} nutrient="protein" /></div></div><PartialNutritionNote recipe={recipe} />
      <div className="flex flex-wrap gap-3"><button className="mm-button" onClick={() => onOpenRecipe ? onOpenRecipe(recipe) : onNavigate('detail')}>View Details</button>
      <button className="mm-button mm-secondary" aria-label={saved ? 'Remove from saved recipes' : 'Save recipe'} disabled={busy} onClick={async () => { setBusy(true); setError(''); try { if (saved) await cloud.remove(saved.id); else await cloud.save(toSavedRecipe(recipe)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }}>{saved ? 'Saved' : 'Save recipe'}</button></div>
      {error && <p role="alert">{error}</p>}<RecipeIntelligence recipe={recipe} /><RecipeOptimization recipe={recipe} onChange={update} />
    </article>}
  </section>;
}
