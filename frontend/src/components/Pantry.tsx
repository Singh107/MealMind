import PantryRecommendations from './PantryRecommendations';
import IngredientAutocomplete from './IngredientAutocomplete';
import { GeneratedRecipe } from '../recipeApi';
import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../AuthContext';
import { deletePantry, listPantry, PantryItem, savePantry } from '../pantryApi';

export default function Pantry({ onNavigate, onOpenRecipe }: { onNavigate: (section: string) => void; onOpenRecipe?: (recipe: GeneratedRecipe) => void }) {
  const { user, loading } = useAuth();
  if (loading) return <p role="status">Restoring your account...</p>;
  if (!user) return <section className="mx-auto max-w-3xl space-y-4 p-6">
    <h1 className="text-3xl font-bold">Pantry</h1><p>Sign in to maintain your pantry across devices.</p>
    <button className="rounded-lg mm-action px-5 py-3" onClick={() => onNavigate('profile')}>Sign in</button>
  </section>;
  return <PantryAccount key={user.id} owner={user.id} onOpenRecipe={onOpenRecipe} />;
}

function PantryAccount({ owner, onOpenRecipe }: { owner: string; onOpenRecipe?: (recipe: GeneratedRecipe) => void }) {
  const [revision, setRevision] = useState(0);
  const [items, setItems] = useState<PantryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [editing, setEditing] = useState<string>();
  const [name, setName] = useState('');
  const [quantity, setQuantity] = useState('');
  const [unit, setUnit] = useState('');
  const active = useRef(true);
  const reload = async () => {
    setLoading(true); setError('');
    try { const rows = await listPantry(owner); if (active.current) setItems(rows); }
    catch (failure) { if (active.current) setError((failure as Error).message); }
    finally { if (active.current) setLoading(false); }
  };
  useEffect(() => {
    active.current = true; void reload();
    return () => { active.current = false; };
    // Account identity is enforced by the keyed component and API owner check.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [owner]);
  const reset = () => { setEditing(undefined); setName(''); setQuantity(''); setUnit(''); };
  const edit = (item: PantryItem) => {
    setEditing(item.id); setName(item.name); setQuantity(item.quantity === null ? '' : String(item.quantity)); setUnit(item.unit || ''); setMessage(''); setError('');
  };
  return <section className="mx-auto max-w-3xl space-y-6 p-4">
    <div><h1 className="text-3xl font-bold">Pantry</h1><p className="mt-2 text-on-surface-variant">Keep track of the ingredients you have. Quantities are optional.</p></div>
    {error && <div role="alert" className="rounded-xl border border-error/30 p-4">{error} <button disabled={busy || loading} onClick={() => void reload()} className="underline">Refresh pantry</button></div>}
    {message && <p role="status">{message}</p>}
    <form className="space-y-4 mm-panel" onSubmit={async event => {
      event.preventDefault(); if (busy || loading) return;
      setBusy(true); setError(''); setMessage('');
      try {
        const row = await savePantry(owner, { name: name.trim(), quantity: quantity === '' ? null : Number(quantity), unit: unit || null }, editing);
        if (active.current) { setItems(rows => editing ? rows.map(r => r.id === row.id ? row : r) : [...rows, row]); reset(); setMessage('Pantry saved.'); setRevision(x => x + 1); }
      } catch (failure) { if (active.current) setError((failure as Error).message); }
      finally { if (active.current) setBusy(false); }
    }}>
      <h2 className="text-xl font-semibold">{editing ? 'Edit ingredient' : 'Add ingredient'}</h2>
      <IngredientAutocomplete value={name} onChange={setName} disabled={busy} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label>Quantity (optional)<input className="block w-full rounded-lg border p-3" type="number" min="0.000001" max="100000" step="any" value={quantity} onChange={e => setQuantity(e.target.value)} disabled={busy} /></label>
        <label>Unit (optional)<select className="block w-full rounded-lg border p-3" value={unit} onChange={e => setUnit(e.target.value)} disabled={busy}>
          <option value="">Unknown</option>{['g','kg','mg','oz','lb','ml','l','tsp','tbsp','cup','piece','clove',...(unit === 'breast' ? ['breast'] : []),'egg','slice','large','medium','small'].map(value => <option key={value} value={value}>{value === 'piece' ? 'pieces / count' : value}</option>)}
        </select></label>
      </div>
      <p className="text-sm text-on-surface-variant">Equivalent entries are kept as one item. Edit its quantity yourself; amounts are never combined automatically.</p>
      <button disabled={busy || loading || !name.trim()} className="rounded-lg mm-action px-5 py-3">{busy ? 'Saving...' : editing ? 'Save changes' : 'Add to pantry'}</button>
      {editing && <button type="button" disabled={busy} onClick={reset} className="ml-4">Cancel edit</button>}
    </form>
    {loading ? <p role="status" className="rounded-2xl bg-surface-container-low p-5 text-on-surface-variant">Loading pantry...</p> : !error && items.length === 0 ? <p className="rounded-2xl border border-dashed border-border bg-surface-container-low p-6 text-center">Your pantry is empty. Add your first ingredient above.</p> : null}
    {!loading && <ul className="space-y-3">{items.map(item => <li key={item.id} className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-surface-container p-4">
      <div className="min-w-0 flex-1"><h2 className="font-semibold break-words">{item.name}</h2><p className="text-sm text-on-surface-variant mt-1">{item.quantity ?? 'Quantity unknown'} {item.unit || ''}</p>
        {item.identity_status === 'unresolved' && <p className="text-sm text-outline">Saved; ingredient matching may need a manual check.</p>}</div>
      <div className="flex flex-wrap gap-2"><button className="rounded-lg border border-border px-3 py-2 text-sm" disabled={busy} aria-label={`Edit ${item.name}`} onClick={() => edit(item)}>Edit</button>
        <button className="rounded-lg px-3 py-2 text-sm text-error" disabled={busy} aria-label={`Delete ${item.name}`} onClick={async () => {
          setBusy(true); setError(''); setMessage('');
          try { await deletePantry(owner, item.id); if (active.current) { setItems(rows => rows.filter(r => r.id !== item.id)); if (editing === item.id) reset(); setMessage('Ingredient removed.'); setRevision(x => x + 1); } }
          catch (failure) { if (active.current) setError((failure as Error).message); }
          finally { if (active.current) setBusy(false); }
        }}>Delete</button></div>
    </li>)}</ul>}
    <PantryRecommendations revision={revision} onOpenRecipe={onOpenRecipe} />
  </section>;
}
