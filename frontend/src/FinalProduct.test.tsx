import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import RecipeGenerator from './components/RecipeGenerator';
import RecipeDetail from './components/RecipeDetail';
import { generateRecipe, parseGenerationResponse, toSavedRecipe } from './recipeApi';
import { readRecipes, saveRecipe } from './recipeStorage';
import { generationFixture, mockGenerationFetch } from './recipeTestFixtures';
import captured from './partialNutritionFixture.json';
import { testAccount } from './accountTestFixtures';
import RecipePantry from './components/RecipePantry';
import { pantryCompatibility } from './pantryApi';
jest.mock('./pantryApi', () => ({ pantryCompatibility: jest.fn() }));

afterEach(() => { cleanup(); localStorage.clear(); jest.restoreAllMocks(); });

test('long custom ingredient keeps its full label and independent removal through preference navigation', () => {
  const name = 'LongCustomIngredient'.repeat(6);
  render(<RecipeGenerator onNavigate={jest.fn()} initialIngredients={[name, 'Broccoli']} />);
  expect(screen.getByText(name)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
  fireEvent.click(screen.getByRole('button', { name: /Back/ }));
  const remove = screen.getByRole('button', { name: `Remove ${name}` });
  remove.focus();
  expect(remove).toHaveFocus();
  fireEvent.click(remove);
  expect(screen.queryByText(name)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Remove Broccoli' })).toBeInTheDocument();
  expect(screen.getByText('Selected Ingredients (1)')).toBeInTheDocument();
});

test('popular control toggles on and off without duplicate selections', () => {
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  const button=screen.getByRole('button',{name:'Chicken Breast'});
  fireEvent.click(button);expect(button).toHaveAttribute('aria-pressed','true');
  expect(screen.getByText('Selected Ingredients (1)')).toBeInTheDocument();
  fireEvent.click(button);expect(button).toHaveAttribute('aria-pressed','false');
  expect(screen.getByText('Selected Ingredients (0)')).toBeInTheDocument();
});

test('curated alias selection shares one toggle identity with Scanner handoff names', () => {
  render(<RecipeGenerator initialIngredients={['rajma','Kidney beans']} onNavigate={jest.fn()} />);
  expect(screen.getByText('Selected Ingredients (1)')).toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'rajma'}});
  const button=within(screen.getByLabelText('Ingredient search results')).getByRole('button',{name:'Kidney beans'});
  expect(button).toHaveAttribute('aria-pressed','true');fireEvent.click(button);
  expect(screen.getByText('Selected Ingredients (0)')).toBeInTheDocument();
});

test('search result remains available to toggle off; browse shares selection', () => {
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'Chicken Breast'}});
  const results=within(screen.getByLabelText('Ingredient search results'));
  fireEvent.click(results.getByRole('button',{name:'Chicken Breast'}));
  expect(results.getByRole('button',{name:'Chicken Breast'})).toHaveAttribute('aria-pressed','true');
  fireEvent.click(results.getByRole('button',{name:'Chicken Breast'}));
  expect(screen.getByText('Selected Ingredients (0)')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/Proteins/}));
  const browse=within(screen.getByRole('group',{name:'Proteins ingredients'}));
  fireEvent.click(browse.getByRole('button',{name:'Chicken Breast'}));
  expect(results.getByRole('button',{name:'Chicken Breast'})).toHaveAttribute('aria-pressed','true');
  fireEvent.click(browse.getByRole('button',{name:'Chicken Breast'}));
  expect(screen.getByText('Selected Ingredients (0)')).toBeInTheDocument();
});

test('calculated partial nutrition, sources and constraints survive serialization and reopened Detail', () => {
  const recipe=parseGenerationResponse(JSON.parse(JSON.stringify(captured))).recipe;
  saveRecipe(toSavedRecipe(recipe));
  const reopened=readRecipes()[0].structuredRecipe!;
  expect(reopened.intelligence).toEqual(recipe.intelligence);
  expect(reopened.intelligence!.nutrition_sources.some(source=>source.food)).toBe(true);
  render(<RecipeDetail generatedRecipe={reopened} onNavigate={jest.fn()} />);
  expect(screen.getByText('267.66 kcal')).toBeInTheDocument();
  expect(screen.getAllByText('Partial data').length).toBeGreaterThan(0);
});

test('generation sends bearer identity and retains server-evaluated restrictions', async () => {
  const request={selected_ingredients:['broccoli'],servings:4, dietary_preferences:[],allergies:[],excluded_ingredients:[]} as any;
  const evaluated={...request,dietary_preferences:['vegetarian'],excluded_ingredients:['mushrooms'],calorie_target:600,cuisine:'Indian'};
  const fetch=mockGenerationFetch({...generationFixture,evaluated_request:evaluated});
  const response=await generateRecipe(request,new AbortController().signal,'test-access');
  expect(fetch.mock.calls[1][1].headers.Authorization).toBe('Bearer test-access');
  expect(response.recipe.original_request).toEqual(evaluated);
});

test('Pantry presence displays a separate uncertain amount', async () => {
  const {Provider}=testAccount();
  (pantryCompatibility as jest.Mock).mockResolvedValue({usable_pantry_count:1,available_count:1,ingredient_count:1,
    ingredients:[{ingredient_index:0,name:'raw chicken breast',status:'available',quantity_status:'unknown',quantity_reason:'No trusted count to grams conversion.'}]});
  render(<Provider><RecipePantry recipe={generationFixture.recipe} /></Provider>);
  expect(await screen.findByText('Check quantity')).toBeInTheDocument();
  expect(screen.getByText('Have')).toBeInTheDocument();
  expect(screen.queryByText('Stated amount sufficient')).not.toBeInTheDocument();
});
