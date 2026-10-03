import React, { useEffect, useState } from 'react';
import { useAuth } from '../AuthContext';
import { GeneratedRecipe } from '../recipeApi';
import { getPantryRecommendations, Recommendations } from '../recommendationApi';

export default function PantryRecommendations({ revision, onOpenRecipe }: {
  revision: number; onOpenRecipe?: (recipe: GeneratedRecipe) => void;
}) {
  const { user } = useAuth();
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<{ owner?: string; data?: Recommendations; error?: string }>({});
  useEffect(() => {
    let active = true; setState({});
    if (user) getPantryRecommendations(user.id).then(data => { if (active) setState({ owner: user.id, data }); })
      .catch(error => { if (active) setState({ owner: user.id, error: error instanceof Error ? error.message : 'Pantry matches are unavailable.' }); });
    return () => { active = false; };
  }, [user?.id, revision, refresh]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!user) return null;
  const data = state.owner === user.id ? state.data : undefined;
  const error = state.owner === user.id ? state.error : undefined;
  return <section aria-label="Recipes from your pantry" className="mm-panel space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">My pantry matches</h2>
      <button className="mm-button mm-secondary" disabled={!data && !error} onClick={() => setRefresh(x => x + 1)}>Refresh matches</button></div>
    <p className="text-sm text-on-surface-variant">From your saved recipes and current preferences. Ingredient presence does not confirm quantities or allergy safety.</p>
    {!data && !error && <p role="status">Finding pantry matches...</p>}
    {error && <p role="alert">{error}</p>}
    {data && <>
      {data.state === 'empty_pantry' && <p>Add recognizable ingredients to your pantry to find matches.</p>}
      {data.state === 'no_candidates' && <p>No saved recipes with ingredient details to compare yet. Create and save a recipe first.</p>}
      {data.state === 'all_ineligible' && <p>Your saved recipes conflict with your current hard restrictions. None are recommended.</p>}
      {data.state === 'only_uncertain' && <p>These recipes need review: ingredient or preference checks remain uncertain.</p>}
      {data.ineligible_count > 0 && <p className="text-sm text-outline">{data.ineligible_count} incompatible recipes excluded.</p>}
      {data.skipped_count > 0 && <p className="text-sm text-outline">{data.skipped_count} saved recipes lack ingredient details for comparison.</p>}
      <ol className="space-y-4">{data.entries.map(entry => <li key={entry.saved_recipe_id} className="rounded-2xl bg-surface-container-low p-4 space-y-3">
        <h3 className="text-lg font-semibold">{entry.recipe.title}</h3>
        <p className={`inline-block rounded-full px-3 py-1 text-sm ${entry.eligibility === 'uncertain' ? 'text-warning bg-surface-container' : 'text-on-surface-variant bg-surface-container'}`}>{entry.eligibility === 'uncertain' ? 'Needs review' : 'Match'}</p>
        <ul className="grid gap-2 text-sm text-on-surface-variant">{entry.reasons.slice(0, 3).map((r, i) => <li className="rounded-xl bg-surface-container p-3" key={i}>{r.text}</li>)}</ul>
        {entry.reasons.length > 3 && <details><summary className="cursor-pointer text-sm text-secondary">More reasons</summary><ul className="text-sm space-y-1 mt-2">{entry.reasons.slice(3).map((r, i) => <li className="rounded-xl bg-surface-container p-3" key={i}>{r.text}</li>)}</ul></details>}
        {onOpenRecipe && <button className="mm-button mm-secondary" onClick={() => onOpenRecipe(entry.recipe)}>View Recipe</button>}
      </li>)}</ol>
      {data.total > data.entries.length && <p className="text-sm text-outline">Showing the first {data.entries.length} of {data.total} matches.</p>}
    </>}
  </section>;
}
