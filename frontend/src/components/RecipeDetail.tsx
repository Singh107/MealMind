import IngredientSubstitutions from './IngredientSubstitutions';
import { useAuth } from '../AuthContext';
import React, { useEffect, useState } from 'react';
import { GeneratedRecipe, toSavedRecipe } from '../recipeApi';
import { useUserData } from '../UserDataContext';
import RecipePantry from './RecipePantry';
import RecipeIntelligence from './RecipeIntelligence';
import RecipeOptimization from './RecipeOptimization';
import NutritionValue, { PartialNutritionNote } from './NutritionValue';
import { Icon } from './DesignShell';

interface Props {
  onNavigate: (section: string) => void;
  generatedRecipe?: GeneratedRecipe | null;
  onRecipeUpdated?: (recipe: GeneratedRecipe) => void;
}
export default function RecipeDetail(props: Props) {
  if (!props.generatedRecipe) return <section className="mm-page space-y-4"><h1>Recipe details</h1><p>Open a saved recipe or generate one to view its ingredients and cooking steps.</p><button className="mm-button" onClick={() => props.onNavigate('generator')}>Create a recipe</button></section>;
  return <StructuredDetail key={props.generatedRecipe.recipe_version_id} {...props} generatedRecipe={props.generatedRecipe} />;
}
function StructuredDetail({ generatedRecipe: initial, onNavigate, onRecipeUpdated }: Props & { generatedRecipe: GeneratedRecipe }) {
  const [recipe, setRecipe] = useState(initial);
  const {user}=useAuth();
  const [substituteIndex,setSubstituteIndex]=useState<number|null>(null);
  const [checked, setChecked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const cloud = useUserData();
  useEffect(() => { setRecipe(initial); setChecked([]); }, [initial]);
  const saved = cloud.recipes.find(row => row.source_id === recipe.recipe_version_id);
  const update = (next: GeneratedRecipe) => { setSubstituteIndex(null); setRecipe(next); setChecked([]); onRecipeUpdated?.(next); };
  const toggleSave = async () => {
    if (busy) return; setBusy(true); setError('');
    try { if (saved) await cloud.remove(saved.id); else await cloud.save(toSavedRecipe(recipe)); }
    catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  };
  return <section id="detail" className="mm-page space-y-5">
    <div className="flex flex-wrap justify-between items-center gap-3"><button className="text-outline flex items-center gap-1" onClick={() => onNavigate('results')}><Icon>arrow_back</Icon>Back to results</button><span className="mm-kicker">Your recipe</span>
      <button className="mm-button mm-secondary" disabled={busy} aria-label={saved ? 'Remove from saved recipes' : 'Save recipe'} onClick={toggleSave}><Icon>{saved ? 'bookmark_added' : 'bookmark_border'}</Icon>{busy ? 'Saving...' : saved ? 'Saved' : 'Save'}</button></div>
    {error && <p role="alert" className="text-error">{error}</p>}
    <div className="mm-panel space-y-4">
      <div className="flex flex-wrap gap-2"><span className="mm-kicker">{recipe.cuisine}</span><span className="text-xs text-outline">{recipe.difficulty}</span></div>
      <h1 className="font-bold">{recipe.title}</h1><p className="text-on-surface-variant">{recipe.description}</p>
      <div className="flex flex-wrap gap-3 text-sm text-on-surface-variant"><span>{recipe.prep_time} min prep</span><span>{recipe.cook_time} min cook</span><span>{recipe.total_time} min total</span><span>{recipe.servings} servings</span></div>
      <p className="text-xs text-outline">{recipe.dietary_tags.join(' / ')}{recipe.dietary_tags.length ? ' / ' : ''}Dietary tags and allergens require ingredient and product-label review.</p>
    </div>
    <div className="mm-panel space-y-4"><h2 className="text-xl font-bold">Nutrition per serving</h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">{(['calories','protein','carbohydrates','fat','fiber','sugar','sodium'] as const).map((nutrient, index) => <div key={nutrient} className="bg-surface-container-low rounded-2xl p-3"><p className="text-xs text-outline mb-2">{['Calories','Protein','Carbs','Fat','Fiber','Sugar','Sodium'][index]}</p><div className="text-lg text-on-surface font-semibold"><NutritionValue recipe={recipe} nutrient={nutrient} /></div></div>)}</div>
      <PartialNutritionNote recipe={recipe} />
      <RecipeIntelligence recipe={recipe} />
    </div>
    <RecipeOptimization recipe={recipe} onChange={update} />
    <RecipePantry recipe={recipe} />
    {recipe.substitution && <section aria-label="Applied substitution" className="mm-panel space-y-3"><h2 className="text-xl font-semibold">Substitution applied</h2><p>{recipe.substitution.change.before.name} to {recipe.substitution.change.after.name}</p><p>{recipe.substitution.message}</p><details><summary>View original recipe before substitution</summary><h3>{recipe.substitution.original_recipe.title}</h3><ul>{recipe.substitution.original_recipe.ingredients.map((x,i)=><li key={i}>{x.quantity} {x.unit} {x.name}</li>)}</ul><ol>{recipe.substitution.original_recipe.instructions.map((x,i)=><li key={i}>{x}</li>)}</ol></details><button className="mm-button mm-secondary" onClick={()=>update(recipe.substitution!.original_recipe)}>Restore original recipe</button></section>}
    {substituteIndex!==null && !recipe.substitution && <IngredientSubstitutions key={`${recipe.recipe_version_id}:${substituteIndex}:${user?.id || 'guest'}`} recipe={recipe} index={substituteIndex} onUse={update} onClose={()=>setSubstituteIndex(null)} />}

    <div className="grid md:grid-cols-2 gap-5">
      <div className="mm-panel"><h2 className="text-xl font-bold mb-4">Ingredients</h2><ul className="space-y-3">{recipe.ingredients.map((item, index) => <li key={index}><label className="mm-check-target flex items-start gap-3"><input type="checkbox" className="mt-1 shrink-0" checked={checked.includes(index)} onChange={() => setChecked(list => list.includes(index) ? list.filter(i => i !== index) : [...list,index])} aria-label={`Check ${item.quantity} ${item.unit} ${item.name}`} /><span className={checked.includes(index) ? 'line-through text-outline' : ''}>{item.quantity} {item.unit} {item.name}</span></label>{!recipe.substitution && <button className="text-xs text-on-surface-variant underline underline-offset-4 min-h-[44px]" onClick={()=>setSubstituteIndex(index)} aria-label={`Find substitutes for ${item.name}`}>Find substitutes</button>}</li>)}</ul></div>
      <div className="mm-panel"><h2 className="text-xl font-bold mb-4">Instructions</h2><ol className="space-y-5">{recipe.instructions.map((step,index) => <li className="flex gap-3" key={index}><span className="shrink-0 w-7 h-7 bg-secondary/15 text-secondary rounded-full flex justify-center items-center text-sm">{index+1}</span><p className="text-sm leading-6 text-on-surface-variant">{step}</p></li>)}</ol></div>
    </div>
    <button className="mm-button mm-secondary" onClick={() => onNavigate('generator')}>Create another recipe</button>
  </section>;
}
