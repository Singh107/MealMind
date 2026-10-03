import React, { useEffect, useState } from 'react';
import { useAuth } from '../AuthContext';
import { PantryCompatibility, pantryCompatibility } from '../pantryApi';
import type { GeneratedRecipe } from '../recipeApi';

export default function RecipePantry({ recipe }: { recipe: GeneratedRecipe }) {
  const { user } = useAuth();
  const serialized = JSON.stringify(recipe.ingredients);
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState<{ owner?: string; key?: string; data?: PantryCompatibility; error?: string }>({});
  useEffect(() => {
    let active = true;
    setState({});
    if (user) pantryCompatibility(user.id, JSON.parse(serialized)).then(data => {
      if (active) setState({ owner: user.id, key: serialized, data });
    }).catch(() => {
      if (active) setState({ owner: user.id, key: serialized, error: 'Pantry coverage is unavailable.' });
    });
    return () => { active = false; };
  }, [user?.id, serialized, retry]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!user || state.owner !== user.id || state.key !== serialized) return null;
  if (state.error) return <p className="mt-4 text-sm text-on-surface-variant">{state.error} <button className="underline" onClick={() => setRetry(n => n + 1)}>Retry pantry check</button></p>;
  const data = state.data;
  if (!data?.usable_pantry_count) return null;
  return <section aria-label="Pantry compatibility" className="my-6 space-y-3 rounded-2xl border border-border bg-surface-container p-4">
    <h2 className="text-lg font-semibold">Pantry match: {data.available_count} / {data.ingredient_count} ingredients available by name</h2>
    <p className="text-sm text-on-surface-variant">Ingredient presence and quantity are separate checks. Coverage includes unknown entries and does not establish allergy safety.</p>
    <div className="grid sm:grid-cols-3 gap-3">{(['available', 'unknown', 'missing'] as const).map(status => <div key={status} className="rounded-xl bg-surface-container-low p-3 space-y-2">
      <h3 className="font-medium">{status === 'available' ? 'Have' : status === 'missing' ? 'Missing' : 'Unknown / check manually'}</h3>
      <ul className="space-y-2 text-sm break-words">{data.ingredients.filter(item => item.status === status).map(item => <li key={item.ingredient_index}>{item.name}{item.status === 'available' && <span className="block text-xs text-on-surface-variant" title={item.quantity_reason}>{item.quantity_status === 'sufficient' ? 'Stated amount sufficient' : item.quantity_status === 'insufficient' ? 'Need more' : 'Check quantity'}</span>}</li>)}</ul>
    </div>)}</div>
  </section>;
}
