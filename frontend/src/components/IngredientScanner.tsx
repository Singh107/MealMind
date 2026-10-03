import React, { useCallback, useEffect, useRef, useState } from 'react';
import PhotoPreview from './PhotoPreview';
import { analyzeIngredients, Detection } from '../visionApi';
import { useAuth } from '../AuthContext';
import { savePantry } from '../pantryApi';

type Row = { id: number; name: string; proposal?: Detection; edited?: boolean };
export default function IngredientScanner({ onNavigate, onCreateRecipe }: { onNavigate: (page: string) => void; onCreateRecipe?: (names: string[]) => void }) {
  const auth = useAuth();
  const owner = auth.user?.id;
  const currentOwner = useRef(owner); currentOwner.current = owner;
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [review, setReview] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [manual, setManual] = useState('');
  const [signIn, setSignIn] = useState(false);
  const [outcomes, setOutcomes] = useState<Record<number, string>>({});
  const controller = useRef<AbortController | null>(null);
  const version = useRef(0); const nextId = useRef(0); const savingLock = useRef(false);
  const stop = useCallback(() => { version.current++; controller.current?.abort(); controller.current = null; savingLock.current = false; }, []);
  useEffect(() => () => { stop(); }, [stop]);
  useEffect(() => {
    stop(); setBusy(false); setSaving(false); setConfirmed(false); setOutcomes({}); setSignIn(false);
  }, [owner, stop]);
  const selectFile = (value: File | null) => {
    stop(); setFile(value); setRows([]); setReview(false); setConfirmed(false); setBusy(false);
    setSaving(false); setOutcomes({}); setError(''); setManual(''); setSignIn(false);
  };
  const analyze = async () => {
    if (!file || controller.current || savingLock.current) return;
    stop(); const sequence = version.current; const active = new AbortController(); controller.current = active;
    setBusy(true); setError(''); setRows([]); setReview(false); setConfirmed(false); setOutcomes({});
    try {
      const result = await analyzeIngredients(file, active.signal);
      if (sequence !== version.current) return;
      setRows(result.detections.map(proposal => ({ id: nextId.current++, proposal,
        name: proposal.display_name + (proposal.visible_state ? `, ${proposal.visible_state}` : '') })));
      setReview(true);
    } catch { if (sequence === version.current) setError('Ingredient analysis could not complete. Please try again or choose another photo.'); }
    finally { if (sequence === version.current) { controller.current = null; setBusy(false); } }
  };
  const edit = (next: Row[]) => { setRows(next); setConfirmed(false); setOutcomes({}); setSignIn(false); };
  const valid = rows.length > 0 && rows.every(row => row.name.trim().length > 0 && row.name.trim().length <= 120);
  const addPantry = async () => {
    if (!confirmed || savingLock.current) return;
    if (!owner) { setSignIn(true); return; }
    const sequence = version.current; savingLock.current = true; setSaving(true);
    try {
      for (const row of rows) {
        if (sequence !== version.current || currentOwner.current !== owner) break;
        if (outcomes[row.id] === 'Added to Pantry' || outcomes[row.id] === 'Already in Pantry') continue;
        let message = '';
        try { await savePantry(owner, { name: row.name.trim(), quantity: null, unit: null }); message = 'Added to Pantry'; }
        catch (e) { message = e instanceof Error && e.message.includes('already in your pantry') ? 'Already in Pantry' : 'Not added. Try again; if it was already saved, Pantry will detect the duplicate.'; }
        if (sequence !== version.current || currentOwner.current !== owner) break;
        setOutcomes(previous => ({ ...previous, [row.id]: message }));
      }
    } finally { if (sequence === version.current) { savingLock.current = false; setSaving(false); } }
  };
  return <PhotoPreview kind="ingredient" onNavigate={onNavigate} onFile={selectFile}>
    {file && <div className="flex flex-wrap gap-3"><button className="mm-button" disabled={busy || saving} onClick={analyze}>Analyze ingredients</button>
      {busy && <><p role="status">Looking for ingredients...</p><button className="mm-button mm-secondary" onClick={() => { stop(); setBusy(false); }}>Cancel analysis</button></>}</div>}
    {error && <p role="alert" className="text-error">{error}</p>}
    {review && <div className="mm-panel space-y-4">
      <h2 className="text-xl font-semibold">{confirmed ? 'Confirmed ingredients' : 'Review ingredient suggestions'}</h2>
      <p className="text-sm text-on-surface-variant">Confidence is the model's self-assessment, not a measured probability. Even a familiar name needs your review.</p>
      {!rows.length && <p>No ingredients identified. Try another photo or add an ingredient yourself.</p>}
      {rows.map((row, index) => <div key={row.id} className="space-y-2 rounded-xl bg-surface-container-low p-4">
        <label className="block">Ingredient {index + 1}<input className="block w-full rounded-xl bg-surface p-3" aria-label={`Ingredient ${index + 1}`} maxLength={120} value={row.name} disabled={saving}
          onChange={e => edit(rows.map(r => r.id === row.id ? { ...r, name: e.target.value, edited: true } : r))} /></label>
        {row.proposal && !row.edited ? <div className="text-sm text-on-surface-variant">
          <p>{row.proposal.confidence === 'high' ? 'Looks like' : row.proposal.confidence === 'medium' ? 'Possibly' : 'Not sure - please review'} {row.proposal.display_name}</p>
          {row.proposal.uncertainty && <p>{row.proposal.uncertainty}</p>}
          <p>{row.proposal.identity_status === 'recognized' ? `Name matched: ${row.proposal.normalized_name}. This does not confirm the photo.` : row.proposal.identity_status === 'conflicting' ? 'Conflicting food states - please correct the name.' : 'Name not matched yet - keep or edit it after checking.'}</p>
        </div> : <p className="text-sm text-on-surface-variant">Your entry - review before confirming.</p>}
        <button className="mm-button mm-secondary" disabled={saving} aria-label={`Remove ingredient ${index + 1}`} onClick={() => edit(rows.filter(r => r.id !== row.id))}>Remove ingredient</button>
        {outcomes[row.id] && <p role="status">{outcomes[row.id]}</p>}
      </div>)}
      <label className="block">Missed ingredient<input className="block w-full rounded-xl bg-surface p-3" maxLength={120} value={manual} disabled={saving} onChange={e => setManual(e.target.value)} /></label>
      <button className="mm-button mm-secondary" disabled={saving || !manual.trim() || rows.length >= 30} onClick={() => { edit([...rows, { id: nextId.current++, name: manual.trim() }]); setManual(''); }}>Add ingredient</button>
      <div><button className="mm-button" disabled={!valid || saving || confirmed} onClick={() => { setConfirmed(true); setError(''); }}>Confirm ingredients</button></div>
      {confirmed && <div className="space-y-3"><p role="status">You confirmed this list. Nothing is saved automatically.</p>
        <div className="flex flex-wrap gap-3"><button className="mm-button" disabled={saving || auth.loading} onClick={addPantry}>{saving ? 'Adding to Pantry...' : 'Add to Pantry'}</button>
          <button className="mm-button mm-secondary" disabled={saving || !onCreateRecipe} onClick={() => onCreateRecipe?.(rows.map(row => row.name.trim()))}>Create recipe with these</button></div>
        {signIn && <p>Sign in to maintain your pantry. <button className="underline" onClick={() => onNavigate('profile')}>Sign in</button></p>}
      </div>}
    </div>}
  </PhotoPreview>;
}
