import { testAccount } from './accountTestFixtures';
import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import App, { AppContent } from './App';
import RecipeIntelligence from './components/RecipeIntelligence';
import { displayNutrition, parseGenerationResponse, toSavedRecipe } from './recipeApi';
import { readRecipes, saveRecipe } from './recipeStorage';
import { mockGenerationFetch } from './recipeTestFixtures';
import fixture from './nutritionTestFixture.json';
import liveFixture from './liveNutritionFixture.json';

let payload: typeof fixture;
beforeEach(() => {
  payload = JSON.parse(JSON.stringify(fixture));
  localStorage.clear();
  window.history.replaceState(null, '', '/#generator');
  window.scrollTo = jest.fn();
});
afterEach(() => { cleanup(); jest.restoreAllMocks(); });

test('captured live Gemini and USDA response preserves partial calculations on save', () => {
  const { recipe } = parseGenerationResponse(JSON.parse(JSON.stringify(liveFixture)));
  expect(displayNutrition(recipe).calories).toBeNull();
  expect(recipe.intelligence!.calculated_nutrition.known_per_serving.calories).toBeCloseTo(284.7539725);
  saveRecipe(toSavedRecipe(recipe));
  const reopened = readRecipes()[0].structuredRecipe!;
  expect(reopened.intelligence).toEqual(recipe.intelligence);
  render(<RecipeIntelligence recipe={reopened} />);
  expect(screen.getByText(/Nutrition partially calculated/)).toBeInTheDocument();
  expect(screen.getByText(/Unable to verify - Protein/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /USDA FDC 2646170/ })).toBeInTheDocument();
});

test('independent calculated nutrition replaces AI display values without changing the legacy estimate', () => {
  const { recipe } = parseGenerationResponse(payload);
  expect(recipe.nutrition.calories).toBe(210);
  expect(displayNutrition(recipe).calories).toBe(125);
  render(<RecipeIntelligence recipe={recipe} />);
  expect(screen.getByText(/Nutrition calculated from USDA/)).toBeInTheDocument();
  expect(screen.getByText(/Passed - Calories: 125 kcal \/ maximum 130 kcal/)).toBeInTheDocument();
  expect(screen.getByText(/Failed - Protein: 12.5 g \/ minimum 40 g/)).toBeInTheDocument();
  expect(screen.getByText(/not been repaired or regenerated/)).toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: /USDA FDC 123/ })).toHaveLength(2);
});

test('partial provenance keeps unknown constraint values conservative', () => {
  const { recipe } = parseGenerationResponse(payload);
  const report = recipe.intelligence!;
  report.nutrition_status = 'partial';
  report.overall_constraint_status = 'partially_verified';
  report.calculated_nutrition.totals.calories = null;
  report.calculated_nutrition.per_serving.calories = null;
  report.nutrition_sources[1].status = 'unmatched';
  report.nutrition_sources[1].reason = 'No food match';
  report.constraint_results = [{ ...report.constraint_results[0], status: 'unknown', passed: null, actual: null, difference: null }];
  render(<RecipeIntelligence recipe={recipe} />);
  expect(displayNutrition(recipe).calories).toBeNull();
  expect(screen.getByText(/Nutrition partially calculated - 1 ingredient incomplete/)).toBeInTheDocument();
  expect(screen.queryByText(/Known subtotal per serving/)).not.toBeInTheDocument();
  expect(screen.getByText(/Unable to verify - Calories: Unknown/)).toBeInTheDocument();
});

test('missing nutrition never falls back to AI values for target checks', () => {
  const { recipe } = parseGenerationResponse(payload);
  recipe.intelligence!.nutrition_status = 'unavailable';
  recipe.intelligence!.calculated_nutrition.per_serving = { calories: null, protein: null, carbohydrates: null, fat: null, fiber: null, sodium: null };
  expect(displayNutrition(recipe).calories).toBeNull();
  render(<RecipeIntelligence recipe={recipe} />);
  expect(screen.getByText(/Calculated nutrition unavailable/)).toBeInTheDocument();
  expect(screen.getByText(/AI estimates are not used/)).toBeInTheDocument();
});

test('verification and food provenance survive local save/reopen', () => {
  const { recipe } = parseGenerationResponse(payload);
  saveRecipe(toSavedRecipe(recipe));
  const saved = readRecipes()[0];
  expect(saved.nutrition.calories).toBe(125);
  expect(saved.structuredRecipe?.intelligence).toEqual(recipe.intelligence);
  expect(saved.structuredRecipe?.nutrition.calories).toBe(210);
});

test('malformed calculated nutrition and false verification flags are rejected', () => {
  for (const altered of [
    { ...fixture, calculated_nutrition: {} },
    { ...fixture, nutrition_sources: [] },
    { ...fixture, constraint_results: [{ ...fixture.constraint_results[0], status: 'passed', passed: false }] },
    { ...fixture, calculated_nutrition: { ...fixture.calculated_nutrition, per_serving: { ...fixture.calculated_nutrition.per_serving, protein: null } } },
  ]) expect(() => parseGenerationResponse(altered)).toThrow('invalid nutrition');
});

test('generator, details and saved recipe render the new evidence without redesigning navigation', async () => {
  const errors = jest.spyOn(console, 'error').mockImplementation(() => {});
  mockGenerationFetch(payload);
  const account = testAccount();
  render(<account.Provider><AppContent /></account.Provider>);
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search for ingredients' }), { target: { value: 'lentil' } });
  fireEvent.click(within(screen.getByLabelText('Ingredient search results')).getByRole('button', { name: 'Lentils' }));
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
  fireEvent.click(screen.getByRole('button', { name: 'Create Recipe' }));
  await screen.findByText(/Failed - Protein: 12.5 g/);
  fireEvent.click(screen.getByRole('button', { name: 'View Recipe Details' }));
  expect(screen.getByRole('heading', { name: 'Your targets' })).toBeInTheDocument();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save recipe' })); });
  act(() => { window.history.replaceState(null, '', '/#saved'); window.dispatchEvent(new HashChangeEvent('hashchange')); });
  fireEvent.click(screen.getByRole('button', { name: 'View details' }));
  expect(screen.getByRole('heading', { name: 'Nutrition verification' })).toBeInTheDocument();
  expect(account.store.rows[0].recipe.structuredRecipe?.intelligence?.overall_constraint_status).toBe('failed');
  cleanup();
  expect(errors.mock.calls).toEqual([]);
  errors.mockRestore();
});
