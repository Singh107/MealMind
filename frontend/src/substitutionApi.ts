import { apiUrl } from './apiConfig';
import { supabase } from './supabase';
import { GeneratedRecipe, RecipeGenerationRequest, isGeneratedRecipe } from './recipeApi';
import { RecipeIntelligence, isRecipeIntelligence } from './nutritionTypes';
export interface SubstitutionCandidate {
  relationship_id: string; name: string; functional_role: string; ratio: number | null; ratio_unit: string | null;
  compatibility: 'compatible' | 'uncertain'; availability: string; reasons: {code:string;text:string}[];
}
export interface SubstitutionBrowse { status:string; message:string; pantry_state:string; candidates:SubstitutionCandidate[]; blocked_count:number }
export interface SubstitutionPreview {
  original_recipe:GeneratedRecipe; final_recipe:GeneratedRecipe; before_intelligence:RecipeIntelligence; after_intelligence:RecipeIntelligence;
  can_use:boolean; message:string; restrictions:RecipeGenerationRequest;
  change:{ingredient_index:number;before:GeneratedRecipe['ingredients'][number];after:GeneratedRecipe['ingredients'][number];relationship_id:string;reason:string};
}
export async function substitutionRequest(recipe:GeneratedRecipe,index:number,owner:string|undefined,signal:AbortSignal,
    choice?:{relationship_id:string;quantity?:number;unit?:string}):Promise<SubstitutionBrowse|SubstitutionPreview> {
  const session=supabase ? (await supabase.auth.getSession()).data.session : null;
  if ((session?.user.id || undefined)!==owner) throw new Error('Your account changed. Reopen substitutions to continue.');
  const {id,recipe_version_id,validation_status,nutrition_source,nutrition_basis,intelligence,optimization,original_request,substitution,...candidate}=recipe;
  const restrictions=original_request || {selected_ingredients:['preference validation']};
  const controller=new AbortController();const abort=()=>controller.abort();
  signal.addEventListener('abort',abort,{once:true});if(signal.aborted)controller.abort();
  let timedOut=false;const timer=setTimeout(()=>{timedOut=true;controller.abort();},35000);
  try {
    const response=await fetch(apiUrl('/api/ingredients/substitutions'+(choice?'/preview':'')),{
      method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json',...(session?{Authorization:`Bearer ${session.access_token}`}:{})},
      body:JSON.stringify({recipe:candidate,ingredient_index:index,restrictions,...choice})});
    if(!response.ok)throw new Error(response.status===422?'This substitution or quantity is not supported with your current restrictions.':'Substitution preview is unavailable. Your original recipe is unchanged.');
    const data=await response.json();
    if(choice){
      if(!isGeneratedRecipe(data.final_recipe)||!isGeneratedRecipe(data.original_recipe)||!isRecipeIntelligence(data.before_intelligence)||!isRecipeIntelligence(data.after_intelligence)||typeof data.can_use!=='boolean'||!data.change||!data.restrictions||data.after_intelligence.calculated_nutrition.servings!==data.final_recipe.servings||data.before_intelligence.calculated_nutrition.servings!==data.original_recipe.servings)throw new Error('Invalid substitution preview. Your original recipe is unchanged.');
    }else if(!Array.isArray(data.candidates)||typeof data.message!=='string')throw new Error('Substitutions could not be read.');
    return data;
  }catch(error){if(timedOut)throw new Error('Substitution preview timed out. Your original recipe is unchanged.');throw error;}
  finally{clearTimeout(timer);signal.removeEventListener('abort',abort);}
}
