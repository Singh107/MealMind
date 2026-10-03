import React, {useEffect,useRef,useState} from 'react';
import { useAuth } from '../AuthContext';
import { GeneratedRecipe, formatNutrient } from '../recipeApi';
import { SubstitutionBrowse, SubstitutionCandidate, SubstitutionPreview, substitutionRequest } from '../substitutionApi';

export default function IngredientSubstitutions({recipe,index,onUse,onClose}:{recipe:GeneratedRecipe;index:number;onUse:(r:GeneratedRecipe)=>void;onClose:()=>void}) {
  const {user}=useAuth();const active=useRef<AbortController|null>(null);
  const [data,setData]=useState<SubstitutionBrowse>();const [preview,setPreview]=useState<SubstitutionPreview>();
  const [choice,setChoice]=useState<SubstitutionCandidate>();const [quantity,setQuantity]=useState('');const [unit,setUnit]=useState('g');
  const [loading,setLoading]=useState(false);const [error,setError]=useState('');
  useEffect(()=>{setData(undefined);setPreview(undefined);setChoice(undefined);setError('');setLoading(false);return ()=>{active.current?.abort();};},[user?.id,recipe.recipe_version_id,index]);
  const request=async (selected?:SubstitutionCandidate)=>{
    active.current?.abort();const controller=new AbortController();active.current=controller;
    setLoading(true);setError('');setPreview(undefined);if(!selected)setChoice(undefined);
    try{
      const result=await substitutionRequest(recipe,index,user?.id,controller.signal,selected?{
        relationship_id:selected.relationship_id,...(selected.ratio===null?{quantity:Number(quantity),unit}:{})}:undefined);
      if(!controller.signal.aborted){if(selected)setPreview(result as SubstitutionPreview);else setData(result as SubstitutionBrowse);}
    }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Substitution unavailable.');}
    finally{if(active.current===controller)setLoading(false);}
  };
  return <section aria-label="Ingredient substitutions" className="mm-panel space-y-4">
    <div className="flex flex-wrap justify-between gap-3"><h2 className="text-xl font-semibold">Substitute {recipe.ingredients[index].name}</h2><button onClick={onClose}>Close substitutes</button></div>
    <p className="text-sm text-outline">Context-specific alternatives for ready-to-assemble meals, dressings, cold toppings and moderate-heat oils. No universal swaps or allergy-safety claims.</p>
    <button className="mm-button mm-secondary" disabled={loading} onClick={()=>void request()}>Find substitutes</button>
    {loading&&<p role="status">{choice?'Recalculating substitution...':'Finding supported alternatives...'}</p>}
    {error&&<p role="alert">{error}</p>}
    {data&&<><p>{data.message}</p>{data.pantry_state==='unavailable'&&<p>Pantry availability could not be checked.</p>}
      {data.blocked_count>0&&<p>{data.blocked_count} alternatives conflict with your restrictions.</p>}
      <ul className="space-y-3">{data.candidates.map(c=><li key={c.relationship_id} className="rounded-2xl bg-surface-container-low p-4 space-y-2">
        <h3 className="font-semibold">{c.name}</h3><p>{c.availability==='available'?'Available in pantry by name/state; quantity not checked.':'Not known in pantry.'}</p>
        <p>{c.compatibility==='uncertain'?'Compatibility could not be fully verified.':'No known restriction conflict.'}</p>
        <p>{c.ratio===null?'Quantity ratio unknown.':`${c.ratio}:1 by ${c.ratio_unit}.`}</p>
        <ul className="text-sm text-on-surface-variant">{c.reasons.map(r=><li key={r.code}>{r.text}</li>)}</ul>
        <button className="mm-button mm-secondary" disabled={loading} onClick={()=>{setChoice(c);setPreview(undefined);setQuantity('');setError('');}}>Select {c.name}</button>
      </li>)}</ul></>}
    {choice&&<form className="space-y-3" onSubmit={e=>{e.preventDefault();void request(choice);}}>
      <p>Selected: {choice.name}</p>
      {choice.ratio===null&&<div className="flex flex-wrap gap-3"><label>Substitute quantity<input aria-label="Substitute quantity" className="block rounded-xl p-2" type="number" required min="0.000001" max="100000" step="any" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>
        <label>Unit<select aria-label="Substitute unit" className="block rounded-xl p-2" value={unit} onChange={e=>setUnit(e.target.value)}>{['g','kg','oz','lb','cup','tbsp','tsp','ml','clove'].map(u=><option key={u}>{u}</option>)}</select></label></div>}
      <button className="mm-button" disabled={loading}>Preview substitution</button>
    </form>}
    {preview&&<section aria-label="Substitution preview" className="space-y-3">
      <h3 className="font-semibold">Original vs substituted</h3><p>{preview.change.before.name}: {preview.change.before.quantity} {preview.change.before.unit} &rarr; {preview.change.after.name}: {preview.change.after.quantity} {preview.change.after.unit}</p>
      <p>{preview.message}</p><p>Nutrition: {preview.before_intelligence.nutrition_status} &rarr; {preview.after_intelligence.nutrition_status}. Incomplete totals remain Unknown.</p>
      <dl>{(['calories','protein','carbohydrates','fat'] as const).map(n=><div key={n}><dt className="capitalize">{n}</dt><dd>{formatNutrient(preview.before_intelligence.calculated_nutrition.per_serving[n])} &rarr; {formatNutrient(preview.after_intelligence.calculated_nutrition.per_serving[n])} {n==='calories'?'kcal':'g'} per serving</dd></div>)}</dl>
      <h4>Constraint checks</h4><ul>{preview.after_intelligence.constraint_results.map((r,i)=><li key={i}>{r.constraint.replace(/_/g,' ')} ({r.requested}): {preview.before_intelligence.constraint_results[i]?.status || 'unknown'} &rarr; {r.status}</li>)}</ul>
      <p className="text-sm text-outline">Cooking instructions must still be reviewed. No taste, texture or general health improvement is claimed.</p>
      <button className="mm-button" disabled={!preview.can_use||loading} onClick={()=>onUse({...preview.final_recipe,intelligence:preview.after_intelligence,original_request:preview.restrictions,
        substitution:{original_recipe:recipe,before_intelligence:preview.before_intelligence,change:preview.change,message:preview.message}})}>Use this version</button>
    </section>}
  </section>;
}
