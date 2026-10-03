import React, { useCallback, useEffect, useRef, useState } from 'react';
import PhotoPreview from './PhotoPreview';
import { analyzeMeal, calculateMeal, MealNutrition } from '../mealApi';
import { Detection } from '../visionApi';
import { NutrientValues } from '../nutritionTypes';

type Component = { id: number; name: string; quantity: string; unit: string; proposal?: Omit<Detection, 'merged_count'>; edited?: boolean };
const nutrients: [keyof NutrientValues, string, string][] = [['calories','Calories','kcal'],['protein','Protein','g'],['carbohydrates','Carbs','g'],['fat','Fat','g'],['fiber','Fiber','g'],['sugar','Sugar','g'],['sodium','Sodium','mg']];
const units = ['g','kg','mg','oz','lb','ml','l','cup','tbsp','tsp','piece','clove','breast','egg','slice','large','medium','small'];

export default function MealAnalyzer({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [file,setFile] = useState<File | null>(null);
  const [rows,setRows] = useState<Component[]>([]);
  const [manual,setManual] = useState('');
  const [confirmed,setConfirmed] = useState(false);
  const [busy,setBusy] = useState<'vision'|'nutrition'|null>(null);
  const [error,setError] = useState('');
  const [empty,setEmpty] = useState(false);
  const [result,setResult] = useState<MealNutrition | null>(null);
  const controller = useRef<AbortController | null>(null); const version=useRef(0); const nextId=useRef(0);
  const invalidate = useCallback(() => { version.current++; controller.current?.abort(); controller.current=null; }, []);
  useEffect(() => () => invalidate(),[invalidate]);
  const edit = (next: Component[]) => { invalidate(); setBusy(null); setRows(next); setConfirmed(false); setResult(null); setError(''); };
  const selectFile = (value: File|null) => { edit([]); setFile(value); setEmpty(false); setManual(''); };
  const identify = async () => {
    if (!file || controller.current) return;
    invalidate(); const sequence=version.current; const active=new AbortController(); controller.current=active;
    setBusy('vision'); setRows([]); setConfirmed(false); setResult(null); setError(''); setEmpty(false);
    try {
      const response=await analyzeMeal(file,active.signal);
      if (version.current!==sequence) return;
      setRows(response.components.map(proposal => ({id:nextId.current++, name:proposal.display_name+(proposal.visible_state ? `, ${proposal.visible_state}` : ''), quantity:'',unit:'',proposal})));
      setEmpty(response.components.length===0);
    } catch { if(version.current===sequence) setError('Meal identification could not complete. Try again or enter foods manually.'); }
    finally { if(version.current===sequence) {controller.current=null;setBusy(null);} }
  };
  const valid = rows.length>0 && rows.every(r => r.name.trim().length>0 && r.name.trim().length<=120);
  const amountsValid = valid && rows.every(r => r.quantity.trim()!=='' && Number.isFinite(Number(r.quantity)) && Number(r.quantity)>0 && Number(r.quantity)<=100000 && units.includes(r.unit));
  const calculate = async () => {
    if (!confirmed || !amountsValid || controller.current) return;
    invalidate(); const sequence=version.current; const active=new AbortController(); controller.current=active;
    setBusy('nutrition');setResult(null);setError('');
    try {
      const response=await calculateMeal(rows.map(r => ({name:r.name.trim(),quantity:Number(r.quantity),unit:r.unit})),active.signal);
      if(version.current===sequence) setResult(response);
    } catch { if(version.current===sequence) setError('Nutrition could not be calculated. Please check the foods and amounts, then try again.'); }
    finally { if(version.current===sequence) {controller.current=null;setBusy(null);} }
  };
  const nutrition=result?.nutrition;
  return <PhotoPreview kind="meal" onNavigate={onNavigate} onFile={selectFile}>
    <ol aria-label="Meal analysis steps" className="flex flex-wrap gap-3 text-sm text-on-surface-variant"><li>1. Add photo</li><li>2. Review foods</li><li>3. Add portions</li><li>4. Calculate nutrition</li></ol>
    {file && <button className="mm-button" disabled={!!busy} onClick={identify}>Analyze meal</button>}
    {busy && <div><p role="status">{busy==='vision' ? 'Looking at meal components...' : 'Calculating from food data...'}</p><button className="mm-button mm-secondary" onClick={() => {invalidate();setBusy(null);}}>Cancel</button></div>}
    {error && <p role="alert" className="text-error">{error}</p>}
    <div className="mm-panel space-y-4"><h2 className="font-bold">Review foods and portions</h2>
      <p className="text-sm text-on-surface-variant">Add foods manually or review the photo suggestions. Include preparation where known; mixed dishes may remain unmatched.</p>
      <p className="text-sm text-on-surface-variant">Confidence is a suggestion, not a measured probability. Hidden ingredients and food safety cannot be confirmed.</p>
      {empty && <p>No foods identified. Enter the components you know below.</p>}
      {!rows.length && !empty && <p className="rounded-xl bg-surface-container-low p-4 text-sm">Start with a photo above, or add a food below. You will enter the amount you ate for each food.</p>}
      {rows.map((row,index) => <div key={row.id} className="border-b border-outline-variant pb-4 space-y-2">
        <label className="block">Food {index+1}<input className="block w-full bg-surface p-3 rounded-xl" maxLength={120} value={row.name} onChange={e => edit(rows.map(r => r.id===row.id ? {...r,name:e.target.value,edited:true} : r))} /></label>
        {row.proposal && !row.edited && <div className="text-sm text-on-surface-variant"><p>{row.proposal.confidence==='high' ? 'Looks like' : row.proposal.confidence==='medium' ? 'Possibly' : 'Not sure - please review'} {row.proposal.display_name}</p><p>{row.proposal.uncertainty}</p>
          <p>{row.proposal.identity_status==='recognized' ? `Name matched: ${row.proposal.normalized_name}. Check the photo yourself.` : row.proposal.identity_status==='conflicting' ? 'Conflicting preparation states - please correct.' : 'Name unresolved - review it; nutrition may remain unavailable.'}</p></div>}
        <div className="grid sm:grid-cols-2 gap-3"><label>Amount eaten {index+1}<input type="number" className="block w-full bg-surface rounded-xl p-3" min="0.001" max="100000" step="any" value={row.quantity} onChange={e => edit(rows.map(r => r.id===row.id ? {...r,quantity:e.target.value} : r))} /></label>
          <label>Unit {index+1}<select className="block w-full bg-surface rounded-xl p-3" value={row.unit} onChange={e => edit(rows.map(r => r.id===row.id ? {...r,unit:e.target.value} : r))}><option value="">Choose a unit</option>{units.map(unit => <option key={unit} value={unit}>{unit}</option>)}</select></label></div>
        <button className="mm-button mm-secondary" onClick={() => edit(rows.filter(r => r.id!==row.id))} aria-label={`Remove food ${index+1}`}>Remove food</button>
      </div>)}
      <label className="block">Add a food<input className="block w-full rounded-xl bg-surface p-3" maxLength={120} value={manual} onChange={e => setManual(e.target.value)} /></label>
      <button className="mm-button mm-secondary" disabled={!manual.trim() || rows.length>=30} onClick={() => {edit([...rows,{id:nextId.current++,name:manual.trim(),quantity:'',unit:''}]);setManual('');}}>Add component</button>
      <p className="text-sm text-on-surface-variant">Enter the amount you ate for each food. Nothing is assumed. Cups and pieces need a matching USDA portion; grams are not inferred from the photo.</p>
      <div className="flex gap-3 flex-wrap"><button className="mm-button" disabled={!valid || confirmed || !!busy} onClick={() => setConfirmed(true)}>Confirm meal</button>
        <button className={`mm-button ${!confirmed ? 'mm-secondary' : ''}`} disabled={!confirmed || !amountsValid || !!busy} onClick={calculate}>Calculate nutrition</button></div>
      {valid && !amountsValid && <p className="text-sm text-on-surface-variant">Add a positive amount and unit for every food before calculating. Confirm again after any edit.</p>}
      {confirmed && <p role="status">Meal confirmed. Any food or portion edit requires confirmation again.</p>}
    </div>
    {nutrition && <section aria-label="Meal nutrition result" className="mm-panel space-y-4"><h2 className="font-bold">Nutrition for your entered amounts</h2>
      <p>{nutrition.nutrition_status==='verified' ? 'Complete core nutrient data' : nutrition.nutrition_status==='partial' ? 'Partial nutrition data' : 'Nutrition unavailable'}</p>
      <p className="text-sm text-on-surface-variant">Calculated from matched USDA records and your entered amounts, not from the photo. Missing components or nutrients remain unknown; these are not certified meal values.</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">{nutrients.map(([key,label,unit]) => {
        const complete=nutrition.calculated_nutrition.totals[key]; const known=nutrition.calculated_nutrition.known_totals[key];
        const partial=complete==null && known!=null && known>0; const value=complete ?? (partial ? known : null);
        return <div key={key} className="bg-surface-container-low p-3 rounded-xl"><h3>{label}</h3><p>{value==null ? 'Unknown' : `${Number(value.toFixed(1))} ${unit}`}</p>{partial && <p className="text-xs">Partial data</p>}</div>;
      })}</div>
      <details><summary className="cursor-pointer font-semibold">Food-data sources</summary>
      {nutrition.nutrition_sources.map(source => <div key={source.ingredient_index} className="text-sm border-b border-outline-variant pb-2"><p>{source.ingredient.name}: {source.status}</p>
        {source.food && <p>USDA FDC {source.food.food_id}: {source.food.description}. Retrieved {source.food.retrieved_at}.</p>}
        {source.ingredient.conversion_evidence && <p>{source.ingredient.conversion_evidence}</p>}{source.reason && <p>{source.reason}</p>}
      </div>)}</details>
    </section>}
  </PhotoPreview>;
}
