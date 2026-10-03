import React, { useEffect, useRef, useState } from 'react';
import { Icon } from './DesignShell';

export default function PhotoPreview({ kind, onNavigate, onFile, children }: { kind: 'ingredient' | 'meal'; onNavigate: (page: string) => void; onFile?: (file: File | null) => void; children?: React.ReactNode }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const scanner = kind === 'ingredient';
  const label = scanner ? 'Upload Ingredient Photo' : 'Upload Meal Photo';
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  const load = (file?: File) => {
    if (!file) return;
    if (!['image/jpeg','image/png','image/webp'].includes(file.type)) { setError('Please upload a valid image file'); return; }
    if (!file.size) { setError('Please choose a non-empty image'); return; }
    if (file.size > 5 * 1024 * 1024) { setError('Image file too large (max 5MB)'); return; }
    setError(''); setUrl(URL.createObjectURL(file)); onFile?.(file);
  };
  return <section className="mm-page space-y-5">
    <p className="mm-kicker">Your photos</p><h1 className="font-bold">{scanner ? 'Scan ingredients' : 'Meal Analyzer'}</h1>
    <p className="text-on-surface-variant">{scanner ? 'Upload a photo and MealMind will suggest the ingredients it can see.' : 'Upload a meal photo, review the foods, enter the portions you ate, and calculate nutrition from food data.'}</p>
    <aside className="rounded-2xl bg-surface-container-low p-4 space-y-2 text-sm text-on-surface-variant">
      <p>{scanner ? 'You review every suggestion before anything is used.' : 'The photo suggests foods, not exact calories or portion sizes.'} Photos are sent to Gemini through MealMind and are not saved by MealMind.</p>
      <p>Photo suggestions do not confirm quantity, allergens, freshness or food safety.</p>
    </aside>
    {error && <p role="alert" className="text-error">{error}</p>}
    <div className={`focus-within:ring-2 focus-within:ring-secondary rounded-3xl border border-dashed p-6 space-y-4 text-center ${dragging ? 'border-secondary bg-secondary/10' : scanner ? 'border-fresh/40 bg-fresh-soft/40' : 'border-sky/40 bg-sky-soft/40'}`}
      onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); load(e.dataTransfer.files[0]); }}>
      <input ref={input} aria-label={label} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={e => { load(e.target.files?.[0]); e.target.value = ''; }} />
      {url ? <img className="w-full max-h-96 object-contain rounded-2xl" src={url} alt={scanner ? 'Ingredient preview' : 'Meal preview'} /> : <div className="py-12 text-outline"><Icon>{scanner ? 'document_scanner' : 'add_photo_alternate'}</Icon><p className="mt-4">Drop a photo here</p><p className="text-sm my-2">or</p><button type="button" className="mm-button" onClick={() => input.current?.click()}>Choose a photo</button><p className="text-xs mt-2">JPEG, PNG or WebP · up to 5 MB</p></div>}
      {url && <div className="flex flex-wrap justify-center gap-3"><button className="mm-button mm-secondary" onClick={() => input.current?.click()}>Choose another photo</button><button className="mm-button mm-secondary" onClick={() => { setUrl(null); setError(''); onFile?.(null); }}>Remove</button></div>}
    </div>
    {children}
    <>{scanner && <button className="mm-button mm-secondary" onClick={() => onNavigate('generator')}>Enter ingredients in Recipe Studio</button>}</>
  </section>;
}
