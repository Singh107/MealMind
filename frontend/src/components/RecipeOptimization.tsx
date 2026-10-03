import React, { useEffect, useRef, useState } from 'react';
import { GeneratedRecipe, formatNutrient } from '../recipeApi';
import { repairRecipe } from '../repairApi';

export default function RecipeOptimization({ recipe, onChange }: {
  recipe: GeneratedRecipe; onChange: (recipe: GeneratedRecipe) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => { active.current?.abort(); active.current = null; }, [recipe.id]);
  const report = recipe.optimization;
  const optimize = async () => {
    if (active.current) return;
    const controller = new AbortController(); active.current = controller;
    setLoading(true); setError('');
    try {
      const result = await repairRecipe(recipe, controller.signal);
      if (controller.signal.aborted || active.current !== controller) return;
      const selected = result.repair_status === 'failed' || result.repair_status === 'not_needed' ? recipe : result.final_recipe;
      onChange({ ...selected, original_request: recipe.original_request,
        intelligence: result.after_intelligence, optimization: result, substitution: recipe.substitution });
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Optimization failed. Your recipe is unchanged.');
    } finally { if (active.current === controller) { active.current = null; setLoading(false); } }
  };
  if (!report && !loading && !error && !(recipe.original_request && recipe.intelligence?.constraint_results.some(r => r.status === 'failed'))) return null;
  return <section className="my-6 rounded-xl border border-border p-5" aria-label="MealMind Optimization">
    <h2 className="text-xl font-bold">MealMind Optimization</h2>
    {!report && <p>Adjust this recipe toward your selected targets, then recalculate and check it. Your original stays available.</p>}
    {!report && recipe.original_request && recipe.intelligence?.constraint_results.some(r => r.status === 'failed') &&
      <button className="mt-3 rounded-xl mm-action px-4 py-2" disabled={loading} onClick={optimize}>
        {loading ? 'Optimizing recipe...' : 'Optimize Recipe'}</button>}
    {!recipe.original_request && !report && <p>Original preferences are unavailable for this older recipe. Generate a new recipe to optimize it.</p>}
    {loading && <p role="status">Recalculating and checking up to two repair attempts...</p>}
    {error && <p role="alert">{error}</p>}
    {report && <>
      <p role={report.repair_status === 'failed' ? 'alert' : 'status'}>{report.message}</p>
      <p>Optimization status: {report.repair_status.replace(/_/g, ' ')}. Attempts: {report.repair_attempts}.</p>
      <dl>{(['calories', 'protein', 'carbohydrates', 'fat'] as const).map(n => <div key={n}>
        <dt className="capitalize">{n}</dt><dd>{formatNutrient(report.before_intelligence.calculated_nutrition.per_serving[n])}
          {' \u2192 '}{formatNutrient(report.after_intelligence.calculated_nutrition.per_serving[n])} {n === 'calories' ? 'kcal' : 'g'} per serving</dd>
      </div>)}</dl>
      <ul>{report.changes.map((c, i) => <li key={i}>{c.ingredient}: {c.before}{' \u2192 '}{c.after}. {c.reason}</li>)}</ul>
      <p>Remaining failed checks: {report.remaining_failed_constraints.map(r => r.constraint.replace(/_/g, ' ')).join(', ') || 'None'}.</p>
      <p>Unknown checks remain unverified. Generic food data cannot certify allergy safety.</p>
      <details><summary className="cursor-pointer font-semibold">View original recipe</summary>
        <h3>{report.original_recipe.title}</h3><p>{report.original_recipe.description}</p>
        <p>{report.original_recipe.servings} servings; {report.original_recipe.prep_time} minutes prep; {report.original_recipe.cook_time} minutes cook.</p>
        <ul>{report.original_recipe.ingredients.map((i, n) => <li key={n}>{i.quantity} {i.unit} {i.name}</li>)}</ul>
        <ol>{report.original_recipe.instructions.map((s, i) => <li key={i}>{s}</li>)}</ol>
      </details>
    </>}
  </section>;
}
