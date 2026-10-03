import { testAccount } from './accountTestFixtures';
import React, { useState } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import RecipeDetail from './components/RecipeDetail';
import RecipeOptimization from './components/RecipeOptimization';
import { GeneratedRecipe } from './recipeApi';
import { repairRecipe, RepairResponse } from './repairApi';
import { generationFixture } from './recipeTestFixtures';
import fixture from './nutritionTestFixture.json';
import { RecipeIntelligence } from './nutritionTypes';
import { readRecipes, saveRecipe } from './recipeStorage';
import { toSavedRecipe } from './recipeApi';

const before = JSON.parse(JSON.stringify(fixture)) as RecipeIntelligence;
before.calculated_nutrition.servings = 4;
before.calculated_nutrition.per_serving.calories = 568;
before.constraint_results = [{ constraint: 'maximum_calories', requested: 500, actual: 568,
  unit: 'kcal', status: 'failed', passed: false, difference: 68, reason: 'Above maximum', evidence: [] }];
const recipe: GeneratedRecipe = { ...generationFixture.recipe, intelligence: before,
  original_request: { selected_ingredients: ['Lentils'], calorie_target: 500, protein_target: null,
    carbs_target: null, fat_target: null, cuisine: null, spice_level: null, max_cooking_time: null,
    difficulty: null, servings: 4, dietary_preferences: [], allergies: [], excluded_ingredients: [], meal_type: null } };
const after = JSON.parse(JSON.stringify(before)) as RecipeIntelligence;
after.calculated_nutrition.per_serving.calories = 492;
after.constraint_results = [{ ...before.constraint_results[0], actual: 492, status: 'passed', passed: true, difference: -8 }];
const response: RepairResponse = { repair_status: 'repaired', repair_attempts: 1,
  original_recipe: generationFixture.recipe, final_recipe: { ...generationFixture.recipe, id: 'repaired-id', title: 'Optimized Stew' },
  before_intelligence: before, after_intelligence: after,
  changes: [{ ingredient: 'Lentils', before: '200 g', after: '180 g', reason: 'Adjusted to address maximum calories.' }],
  remaining_failed_constraints: [], message: 'The selected recipe passes the calculated constraint checks.',
  failure_code: null, trace_id: 'repair-test' };
function Harness() {
  const [value, setValue] = useState(recipe);
  return <><h1>{value.title}</h1><RecipeOptimization recipe={value} onChange={setValue} /></>;
}
beforeEach(() => { localStorage.clear(); global.fetch = jest.fn(); });
const respond = (value: unknown) => (global.fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => value });

test('Optimize Recipe, loading, repaired values, changes and original remain visible', async () => {
  let resolve: (value: any) => void = () => {};
  (global.fetch as jest.Mock).mockReturnValue(new Promise(r => { resolve = r; }));
  render(<Harness />);
  fireEvent.click(screen.getByRole('button', { name: 'Optimize Recipe' }));
  expect(screen.getByRole('button', { name: 'Optimizing recipe...' })).toBeDisabled();
  await act(async () => resolve({ ok: true, json: async () => response }));
  expect(await screen.findByRole('heading', { name: 'Optimized Stew' })).toBeInTheDocument();
  expect(screen.getByText(/568.*492/)).toBeInTheDocument();
  expect(screen.getByText(/200 g.*180 g/)).toBeInTheDocument();
  fireEvent.click(screen.getByText('View original recipe'));
  expect(screen.getByRole('heading', { name: generationFixture.recipe.title })).toBeInTheDocument();
});

test('provider failure preserves recipe and before values', async () => {
  respond({ ...response, repair_status: 'failed', final_recipe: response.original_recipe,
    after_intelligence: before, changes: [], message: 'The recipe AI is temporarily unavailable. Please try again.' });
  render(<Harness />); fireEvent.click(screen.getByText('Optimize Recipe'));
  expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable');
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(recipe.title);
  expect(screen.getByText(/568.*568/)).toBeInTheDocument();
});

test('malformed repair response leaves original intact', async () => {
  respond({ repair_status: 'repaired' }); render(<Harness />);
  fireEvent.click(screen.getByText('Optimize Recipe'));
  expect(await screen.findByRole('alert')).toHaveTextContent('invalid optimization');
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(recipe.title);
});

test('unmount cancels and ignores stale repair', async () => {
  let resolve: (v: any) => void = () => {};
  (global.fetch as jest.Mock).mockReturnValue(new Promise(r => { resolve = r; }));
  const change = jest.fn(); const view = render(<RecipeOptimization recipe={recipe} onChange={change} />);
  fireEvent.click(screen.getByText('Optimize Recipe')); view.unmount();
  await act(async () => resolve({ ok: true, json: async () => response }));
  expect(change).not.toHaveBeenCalled();
  expect((global.fetch as jest.Mock).mock.calls[0][1].signal.aborted).toBe(true);
});

test('request strips server metadata and preserves original preferences', async () => {
  respond(response); await repairRecipe(recipe, new AbortController().signal);
  const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
  expect(url).toMatch(/api\/recipes\/repair$/);
  const body = JSON.parse(options.body);
  expect(body.recipe.id).toBeUndefined(); expect(body.recipe.intelligence).toBeUndefined();
  expect(body.constraints.calorie_target).toBe(500);
});

test('optimized recipe and original survive save/reload', () => {
  saveRecipe(toSavedRecipe({ ...response.final_recipe, intelligence: after, original_request: recipe.original_request, optimization: response }));
  const loaded = readRecipes()[0].structuredRecipe!;
  expect(loaded.optimization?.original_recipe.title).toBe(recipe.title);
  expect(loaded.intelligence?.calculated_nutrition.per_serving.calories).toBe(492);
});

test('older recipes cannot optimize without preferences', () => {
  render(<RecipeOptimization recipe={generationFixture.recipe} onChange={jest.fn()} />);
  expect(screen.queryByText('Optimize Recipe')).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'MealMind Optimization' })).not.toBeInTheDocument();
});


test('detail optimization saves selected version and keeps original in saved metadata', async () => {
  respond(response);
  const account = testAccount();
  render(<account.Provider><RecipeDetail generatedRecipe={recipe} onNavigate={jest.fn()} /></account.Provider>);
  fireEvent.click(screen.getByText('Optimize Recipe'));
  await screen.findByText(/Optimization status: repaired/);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save recipe' })); });
  const saved = account.store.rows[0].recipe.structuredRecipe!;
  expect(saved.title).toBe('Optimized Stew');
  expect(saved.optimization?.original_recipe.title).toBe(recipe.title);
});
