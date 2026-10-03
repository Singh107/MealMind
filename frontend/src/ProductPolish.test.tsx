import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import KitchenHome from './components/KitchenHome';
import Profile from './components/Profile';
import SavedRecipes from './components/SavedRecipes';
import RecipeIntelligence from './components/RecipeIntelligence';
import RecipeOptimization from './components/RecipeOptimization';
import { testAccount } from './accountTestFixtures';
import { useUserData } from './UserDataContext';
import { parseGenerationResponse } from './recipeApi';
import { saveRecipe } from './recipeStorage';
import fixture from './nutritionTestFixture.json';

beforeEach(()=>{ localStorage.clear(); window.scrollTo=jest.fn(); });

test('Home describes implemented photo flows truthfully and preserves routes',()=>{
  const navigate=jest.fn(); render(<KitchenHome onNavigate={navigate} />);
  expect(screen.queryByText(/not connected|Photo preview/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/Identify ingredients from a photo/}));
  expect(navigate).toHaveBeenLastCalledWith('scanner');
  fireEvent.click(screen.getByRole('button',{name:/Identify foods from a meal photo/}));
  expect(navigate).toHaveBeenLastCalledWith('analyzer');
});

test('grouped Profile preserves preference payload and has one Edit Profile action',async()=>{
  const account=testAccount();
  function Probe(){ return <output data-testid="preferences">{JSON.stringify(useUserData().preferences)}</output>; }
  render(<account.Provider><Profile onNavigate={jest.fn()} /><Probe /></account.Provider>);
  expect(screen.getAllByRole('button',{name:'Edit Profile'})).toHaveLength(1);
  for(const name of ['Account','Dietary preferences','Ingredients and cuisine','Nutrition targets'])
    expect(screen.getByRole('region',{name})).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('Vegan'));
  fireEvent.change(screen.getByLabelText('Other allergies (comma-separated)'),{target:{value:'sesame, shellfish'}});
  fireEvent.change(screen.getByLabelText('Excluded ingredients (comma-separated)'),{target:{value:'onion, garlic'}});
  fireEvent.change(screen.getByLabelText('Preferred cuisines (comma-separated)'),{target:{value:'Indian, Thai'}});
  fireEvent.change(screen.getByLabelText('Maximum calories (kcal)'),{target:{value:'500'}});
  await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Save preferences'})));
  const value=JSON.parse(screen.getByTestId('preferences').textContent!);
  expect(value.dietary_preferences).toContain('vegan');
  expect(value.allergies).toEqual(['sesame','shellfish']);
  expect(value.excluded_ingredients).toEqual(['onion','garlic']);
  expect(value.preferred_cuisines).toEqual(['Indian','Thai']);
  expect(value.nutrition_targets.calorie_target).toBe(500);
});

test('target and provenance disclosures retain exact evidence and visible warning',()=>{
  const {recipe}=parseGenerationResponse(JSON.parse(JSON.stringify(fixture)));
  recipe.intelligence!.potential_allergen_warnings=['Potential allergen: check product labels.'];
  render(<RecipeIntelligence recipe={recipe} />);
  expect(screen.getByText("Doesn't meet selected targets")).toBeVisible();
  expect(screen.getByText('Potential allergen: check product labels.')).toBeVisible();
  for(const name of ['Target details','Food sources and unresolved ingredients']) {
    const summary=screen.getByText(name); const disclosure=summary.closest('details')!;
    expect(disclosure.open).toBe(false); fireEvent.click(summary); expect(disclosure.open).toBe(true);
  }
  expect(screen.getByText(/Failed - Protein/)).toBeVisible();
  expect(screen.getAllByRole('link',{name:/USDA FDC 123/})).toHaveLength(2);
});

test('non-actionable optimization is absent without changing failed-check eligibility',()=>{
  const {recipe}=parseGenerationResponse(JSON.parse(JSON.stringify(fixture)));
  recipe.intelligence!.constraint_results=[];
  render(<RecipeOptimization recipe={recipe} onChange={jest.fn()} />);
  expect(screen.queryByRole('region',{name:'MealMind Optimization'})).not.toBeInTheDocument();
});

test('Saved ingredient preview is bounded and full list is accessible',()=>{
  const ingredients=Array.from({length:8},(_,i)=>`Food ${i+1}`);
  saveRecipe({name:'Saved meal',ingredients,instructions:'Cook carefully.',prepTime:'5 min',cookTime:'10 min',servings:2,difficulty:'Easy',nutrition:{calories:200,protein:10,carbs:20,fat:5}});
  render(<SavedRecipes onNavigate={jest.fn()} />);
  expect(screen.getByText('+3 more')).toBeInTheDocument();
  expect(screen.queryByText('Food 8')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'View details'}));
  expect(screen.getByText('Food 8')).toBeVisible();
  expect(within(screen.getByText('Food 8').closest('ul')!).getAllByRole('listitem')).toHaveLength(8);
});
