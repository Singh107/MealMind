import React from 'react';
import { GeneratedRecipe, nutritionLabel } from '../recipeApi';
import { ConstraintResult } from '../nutritionTypes';

function targetText(result: ConstraintResult) {
  const labels: Record<string, string> = { calories: 'Calories', protein: 'Protein', carbohydrates: 'Carbs', fat: 'Fat', cooking_time: 'Cooking time' };
  const prefix = result.constraint.startsWith('minimum_') ? 'minimum' : 'maximum';
  const name = result.constraint.replace(/^(minimum|maximum)_/, '');
  if (labels[name]) return `${labels[name]}: ${result.actual ?? 'Unknown'} ${result.unit || ''} / ${prefix} ${result.requested} ${result.unit || ''}`;
  return `${result.constraint.replace(/_/g, ' ')}: ${result.requested}${result.actual ? ` (${result.actual})` : ''}`;
}

export default function RecipeIntelligence({ recipe }: { recipe: GeneratedRecipe }) {
  const report = recipe.intelligence;
  if (!report) return null;
  const incomplete = report.nutrition_sources.filter(source => source.status !== 'calculated').length;
  return <div className="mt-6 space-y-4 border-t border-border pt-6 text-sm text-on-surface-variant">
    <h3 className="text-lg font-semibold text-on-surface">Nutrition verification</h3>
    <p>{nutritionLabel(recipe)}{incomplete > 0 ? ` - ${incomplete} ingredient${incomplete === 1 ? '' : 's'} incomplete.` : '.'}</p>
    <h3 className="text-lg font-semibold text-on-surface">Your targets</h3>
    <p className="font-medium text-on-surface">{!report.constraint_results.length ? 'No targets selected' : report.constraint_results.some(r=>r.status==='failed') ? "Doesn't meet selected targets" : report.constraint_results.some(r=>r.status==='unknown') || report.overall_constraint_status !== 'passed' ? 'Needs review' : 'Meets selected targets'}</p>
    <p className="text-xs">Cooking time is a recipe estimate.</p>
    {report.constraint_results.length ? <details><summary className="cursor-pointer font-semibold">Target details</summary><ul className="space-y-3">{report.constraint_results.map((result, index) => <li key={index}>
      <p className={result.status === 'failed' ? 'font-semibold text-error' : result.status === 'passed' ? 'font-semibold text-success' : 'font-semibold text-warning'}>
        {result.status === 'passed' ? 'Passed' : result.status === 'failed' ? 'Failed' : 'Unable to verify'} - {targetText(result)}
      </p><p>{result.reason}</p>
    </li>)}</ul></details> : <p>No explicit targets were selected.</p>}
    {report.overall_constraint_status === 'failed' && <p>This recipe did not meet all requested constraints. Review it or change your inputs; it has not been repaired or regenerated automatically.</p>}
    {report.potential_allergen_warnings.length > 0 && <div><h3 className="font-semibold">Potential allergens</h3>
      <ul className="list-disc pl-5">{report.potential_allergen_warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
    <p>Generic food data cannot verify allergy safety or cross-contact. Check ingredient and product labels.</p>
    <details><summary className="cursor-pointer font-semibold">Food sources and unresolved ingredients</summary>
          <p>{report.nutrition_status === 'verified'
      ? 'Every ingredient has a food match, gram weight, and calorie/protein/carbs/fat data. These are food-data calculations, not laboratory measurements of your meal.'
      : 'Unknown nutrients are not treated as zero. AI estimates are not used to check your targets.'}</p>
      <ul className="mt-3 space-y-3">{report.nutrition_sources.map(source => <li key={source.ingredient_index}>
        <p className="font-medium">{source.ingredient.original_text}</p>
        {source.food && <p><a className="underline" href={`https://fdc.nal.usda.gov/food-details/${source.food.food_id}/nutrients`} target="_blank" rel="noreferrer">USDA FDC {source.food.food_id}: {source.food.description}</a>
          {' '}({source.food.match_quality.replace(/_/g, ' ')}; retrieved {source.food.retrieved_at})</p>}
        {source.ingredient.conversion_evidence && <p>{source.ingredient.conversion_evidence}</p>}
        {source.reason && <p>Unable to fully calculate: {source.reason}</p>}
      </li>)}</ul>
    </details>
  </div>;
}
