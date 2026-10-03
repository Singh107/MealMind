import React from 'react';
import { act,fireEvent,render,screen,within } from '@testing-library/react';
import IngredientSubstitutions from './components/IngredientSubstitutions';
import RecipeDetail from './components/RecipeDetail';
import { substitutionRequest } from './substitutionApi';
import { generationFixture } from './recipeTestFixtures';
import fixture from './nutritionTestFixture.json';
import { RecipeIntelligence } from './nutritionTypes';
import { GeneratedRecipe,toSavedRecipe } from './recipeApi';
import { saveRecipe,readRecipes } from './recipeStorage';
import { AuthContext,AuthState } from './AuthContext';

jest.mock('./substitutionApi',()=>({substitutionRequest:jest.fn()}));
const request=substitutionRequest as jest.Mock;
const recipe:GeneratedRecipe={...generationFixture.recipe,title:'Grain bowl',ingredients:[{name:'cooked brown rice',quantity:1,unit:'cup'}],instructions:['Layer cooked brown rice.']};
const candidate={relationship_id:'grain_base:brown_rice:quinoa',name:'cooked quinoa',functional_role:'grain_base',ratio:1,ratio_unit:'cup',compatibility:'compatible',availability:'available',reasons:[{code:'role',text:'Supported cooked grain alternative.'}]};
const browse={status:'ready',message:'Choose an alternative.',pantry_state:'loaded',blocked_count:0,candidates:[candidate]};
const before=JSON.parse(JSON.stringify(fixture)) as RecipeIntelligence;before.calculated_nutrition.servings=4;
const after=JSON.parse(JSON.stringify(before)) as RecipeIntelligence;after.calculated_nutrition.per_serving.calories=222;
const preview={original_recipe:recipe,final_recipe:{...recipe,id:'variant',recipe_version_id:'variant-version',ingredients:[{name:'cooked quinoa',quantity:1,unit:'cup'}]},
  before_intelligence:before,after_intelligence:after,can_use:true,message:'Review the evidence.',restrictions:{selected_ingredients:['preference validation']},
  change:{ingredient_index:0,before:recipe.ingredients[0],after:{name:'cooked quinoa',quantity:1,unit:'cup'},relationship_id:candidate.relationship_id,reason:'Selected alternative.'}};
const panel=(onUse=jest.fn())=><IngredientSubstitutions recipe={recipe} index={0} onUse={onUse} onClose={jest.fn()}/>;
beforeEach(()=>{jest.resetAllMocks();localStorage.clear();request.mockResolvedValue(browse);});
async function choose(){fireEvent.click(screen.getByRole('button',{name:'Find substitutes'}));fireEvent.click(await screen.findByRole('button',{name:'Select cooked quinoa'}));}

test('Detail ingredient action opens substitutions without mutating recipe',()=>{
  render(<RecipeDetail generatedRecipe={recipe} onNavigate={jest.fn()}/>);
  fireEvent.click(screen.getByRole('button',{name:'Find substitutes for cooked brown rice'}));
  expect(screen.getByRole('region',{name:'Ingredient substitutions'})).toBeInTheDocument();
  expect(request).not.toHaveBeenCalled();
});

test('candidates show pantry and ratio; preview requires deliberate use',async()=>{
  const use=jest.fn();render(panel(use));await choose();
  expect(screen.getByText(/Available in pantry by name/)).toBeInTheDocument();
  expect(screen.getByText('1:1 by cup.')).toBeInTheDocument();
  request.mockResolvedValue(preview);fireEvent.click(screen.getByRole('button',{name:'Preview substitution'}));
  const region=await screen.findByRole('region',{name:'Substitution preview'});
  expect(within(region).getByText(/222/)).toBeInTheDocument();expect(use).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Use this version'}));
  expect(use.mock.calls[0][0].substitution.original_recipe).toEqual(recipe);
  expect(use.mock.calls[0][0].intelligence).toEqual(after);
});

test('unknown ratio requires explicit quantity',async()=>{
  request.mockResolvedValue({...browse,candidates:[{...candidate,ratio:null}]});render(panel());await choose();
  expect(screen.getByLabelText('Substitute quantity')).toBeRequired();
  fireEvent.change(screen.getByLabelText('Substitute quantity'),{target:{value:'150'}});
  request.mockResolvedValue(preview);fireEvent.click(screen.getByRole('button',{name:'Preview substitution'}));
  await screen.findByRole('region',{name:'Substitution preview'});
  expect(request.mock.calls[1][4]).toEqual({relationship_id:candidate.relationship_id,quantity:150,unit:'g'});
});

test.each(['unsupported_context','no_candidates'])('%s states remain honest',async status=>{
  request.mockResolvedValue({...browse,status,candidates:[],blocked_count:2,message:'No supported alternatives.'});render(panel());
  fireEvent.click(screen.getByRole('button',{name:'Find substitutes'}));
  expect(await screen.findByText('No supported alternatives.')).toBeInTheDocument();
  expect(screen.getByText(/2 alternatives conflict/)).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Preview substitution'})).not.toBeInTheDocument();
});

test('loading and provider failure retain original',async()=>{
  render(panel());await choose();let reject:any;request.mockReturnValue(new Promise((_,r)=>{reject=r;}));
  fireEvent.click(screen.getByRole('button',{name:'Preview substitution'}));expect(screen.getByRole('status')).toBeInTheDocument();
  await act(async()=>{reject(new Error('Preview unavailable. Original unchanged.'));});
  expect(screen.getByRole('alert')).toHaveTextContent('Original unchanged');expect(screen.queryByRole('button',{name:'Use this version'})).not.toBeInTheDocument();
});

test('uncertain hard checks cannot be used',async()=>{
  render(panel());await choose();request.mockResolvedValue({...preview,can_use:false,message:'Compatibility unresolved.'});
  fireEvent.click(screen.getByRole('button',{name:'Preview substitution'}));
  expect(await screen.findByRole('button',{name:'Use this version'})).toBeDisabled();
});

test('original and change survive save/reopen and restore',()=>{
  const variant:GeneratedRecipe={...preview.final_recipe,intelligence:after,substitution:{original_recipe:recipe,before_intelligence:before,change:preview.change,message:preview.message}};
  saveRecipe(toSavedRecipe(variant));const restored=readRecipes()[0].structuredRecipe!;
  expect(restored.substitution?.original_recipe).toEqual(recipe);
  render(<RecipeDetail generatedRecipe={restored} onNavigate={jest.fn()}/>);
  expect(screen.getByText('View original recipe before substitution')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Restore original recipe'}));
  expect(screen.getByRole('button',{name:'Find substitutes for cooked brown rice'})).toBeInTheDocument();
  expect(screen.queryByRole('region',{name:'Applied substitution'})).not.toBeInTheDocument();
});

test('account changes discard late substitution results',async()=>{
  let resolve:any;request.mockReturnValue(new Promise(r=>{resolve=r;}));
  const auth={user:{id:'a'},signedIn:true} as AuthState;
  const view=render(<AuthContext.Provider value={auth}>{panel()}</AuthContext.Provider>);
  fireEvent.click(screen.getByRole('button',{name:'Find substitutes'}));
  view.rerender(<AuthContext.Provider value={{...auth,user:{id:'b'} as any}}>{panel()}</AuthContext.Provider>);
  await act(async()=>{resolve(browse);});
  expect(screen.queryByText('cooked quinoa')).not.toBeInTheDocument();
  expect(request.mock.calls[0][3].aborted).toBe(true);
});
