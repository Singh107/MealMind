import { testAccount } from './accountTestFixtures';
import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import App, { AppContent } from './App';
import RecipeGenerator from './components/RecipeGenerator';
import { generateRecipe, parseGenerationResponse, RecipeGenerationRequest, toSavedRecipe } from './recipeApi';
import { readRecipes, saveRecipe } from './recipeStorage';
import { generationFixture, mockGenerationFetch } from './recipeTestFixtures';
import { normalizeApiBase, apiUrl } from './apiConfig';

const request: RecipeGenerationRequest = {
  selected_ingredients: ['Lentils'], calorie_target: null, protein_target: null, carbs_target: null,
  fat_target: null, cuisine: null, spice_level: null, max_cooking_time: null, difficulty: null,
  servings: 4, dietary_preferences: [], allergies: [], excluded_ingredients: [], meal_type: null,
};
let consoleErrors: jest.SpyInstance;
beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, '', '/#generator');
  window.scrollTo = jest.fn();
  consoleErrors = jest.spyOn(console, 'error').mockImplementation(() => {});
  mockGenerationFetch();
});
afterEach(() => {
  cleanup();
  jest.useRealTimers();
  expect(consoleErrors.mock.calls).toEqual([]);
  jest.restoreAllMocks();
});

function enterPreferences() {
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search for ingredients' }), { target: { value: 'Lentil' } });
  fireEvent.click(within(screen.getByLabelText('Ingredient search results')).getByRole('button', { name: 'Lentils' }));
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
}

test('API base uses a local default and preserves deployment prefixes without duplicate slashes', () => {
  expect(normalizeApiBase()).toBe('http://127.0.0.1:8000');
  expect(normalizeApiBase(' https://example.org/mealmind/// ')).toBe('https://example.org/mealmind');
  expect(apiUrl('/health')).toMatch(/\/health$/);
});

test.each([
  [502, 'provider_failure', 'The recipe AI is temporarily unavailable'],
  [422, 'invalid_request', 'Some recipe preferences are invalid'],
  [504, 'provider_timeout', 'Recipe generation took too long'],
])('HTTP %s shows the correct user-facing error after a successful health check', async (status, code, message) => {
  const calls = mockGenerationFetch({ error: { code, message: 'private provider details' } }, status as number);
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  enterPreferences();
  fireEvent.click(screen.getByRole('button', { name: 'Create Recipe' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(message as string);
  expect(screen.getByRole('alert')).not.toHaveTextContent('private');
  expect(calls.mock.calls.map(([url]) => url)).toEqual([apiUrl('/health'), apiUrl('/api/recipes/generate')]);
});

test('unreachable backend displays a connection error and never submits generation', async () => {
  global.fetch = jest.fn().mockRejectedValue(new TypeError('network error'));
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  enterPreferences();
  fireEvent.click(screen.getByRole('button', { name: 'Create Recipe' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('cannot reach the local server');
  expect(global.fetch).toHaveBeenCalledTimes(1);
});

test('serializes all existing form controls, preserves zero, and shows actual response values', async () => {
  const fetchMock = mockGenerationFetch();
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  enterPreferences();
  for (const [label, value] of [['Target Calories (per serving)', '500'], ['Protein (g)', '40'], ['Carbs (g)', '0'], ['Fat (g)', '20'],
    ['Cuisine Type', 'indian'], ['Spice Level', 'spicy'], ['Max Cook Time', '30'], ['Difficulty', 'beginner'], ['Servings', '4'], ['Meal Type', 'dinner']]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.click(screen.getByLabelText('Vegan'));
  fireEvent.click(screen.getByLabelText('Peanuts'));
  fireEvent.change(screen.getByLabelText('Excluded ingredients (comma-separated)'), { target: { value: ' mushrooms, olives ' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create Recipe' }));
  expect(screen.getByRole('status')).toHaveTextContent('Generating');
  expect(await screen.findByRole('heading', { name: generationFixture.recipe.title })).toBeInTheDocument();
  const [url, options] = fetchMock.mock.calls.find(([url]) => url.endsWith('/api/recipes/generate'))!;
  expect(url).toMatch(/\/api\/recipes\/generate$/);
  expect(options.method).toBe('POST');
  expect(options.headers).toEqual({ 'Content-Type': 'application/json' });
  expect(JSON.parse(options.body)).toEqual({
    selected_ingredients: ['Lentils'], calorie_target: 500, protein_target: 40, carbs_target: 0, fat_target: 20,
    cuisine: 'indian', spice_level: 'spicy', max_cooking_time: 30, difficulty: 'beginner', servings: 4,
    dietary_preferences: ['vegan'], allergies: ['peanuts'], excluded_ingredients: ['mushrooms', 'olives'], meal_type: 'dinner',
  });
  expect(screen.getByText('210')).toBeInTheDocument();
  expect(screen.getByText('200 g Lentils')).toBeInTheDocument();
  expect(screen.getByText('Rinse lentils and dice tomatoes.')).toBeInTheDocument();
});

test('error retains preferences and retry succeeds without fabricating a recipe', async () => {
  const fetchMock = mockGenerationFetch({ error: { message: 'Configure GEMINI_API_KEY on the backend.', field_issues: [] } }, 503);
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  enterPreferences();
  fireEvent.click(screen.getByLabelText('Vegan'));
  fireEvent.click(screen.getByRole('button', { name: 'Create Recipe' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('recipe AI is temporarily unavailable');
  expect(screen.getByLabelText('Vegan')).toBeChecked();
  expect(screen.queryByText('Your Custom Recipe')).not.toBeInTheDocument();
  fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => generationFixture });
  fireEvent.click(screen.getByRole('button', { name: 'Create Recipe' }));
  expect(await screen.findByText(generationFixture.recipe.title)).toBeInTheDocument();
});

test('create, results, detail, save, reopen and unsave use the same structured recipe', async () => {
  const account = testAccount();
  render(<account.Provider><AppContent /></account.Provider>);
  enterPreferences();
  fireEvent.click(screen.getByRole('button', { name: 'Create Recipe' }));
  await screen.findByText(generationFixture.recipe.title);
  act(() => { window.location.hash = 'results'; window.dispatchEvent(new HashChangeEvent('hashchange')); });
  expect(screen.getByText(generationFixture.recipe.title)).toBeInTheDocument();
  expect(screen.queryByText('Creamy Tuscan Chicken Pasta')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /View Details/ }));
  expect(screen.queryByRole('img', { name: generationFixture.recipe.title })).not.toBeInTheDocument();
  expect(screen.getByText('Rinse lentils and dice tomatoes.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('checkbox', { name: 'Check 200 g Lentils' }));
  expect(screen.getByRole('checkbox', { name: 'Check 200 g Lentils' })).toBeChecked();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save recipe' })); });
  expect(account.store.rows[0].recipe.structuredRecipe).toEqual({ ...generationFixture.recipe,
    original_request: JSON.parse((global.fetch as jest.Mock).mock.calls.find(([url]) => String(url).endsWith('/api/recipes/generate'))![1].body),
  });
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: /Saved/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Open full recipe' }));
  expect(screen.getByRole('heading', { name: generationFixture.recipe.title })).toBeInTheDocument();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Remove from saved recipes' })); });
  expect(account.store.rows).toEqual([]);
});

test('cancels on Back and ignores a stale response', async () => {
  let resolve!: (response: unknown) => void;
  global.fetch = jest.fn(() => new Promise(done => { resolve = done; })) as jest.Mock;
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  enterPreferences();
  fireEvent.click(screen.getByRole('button', { name: 'Create Recipe' }));
  const signal = (global.fetch as jest.Mock).mock.calls[0][1].signal;
  fireEvent.click(screen.getByRole('button', { name: /Back to Ingredients/ }));
  expect(signal.aborted).toBe(true);
  await act(async () => { resolve({ ok: true, status: 200, json: async () => generationFixture }); });
  expect(screen.getByRole('searchbox')).toBeInTheDocument();
  expect(screen.queryByText(generationFixture.recipe.title)).not.toBeInTheDocument();
});

test('API client rejects network, non-JSON and malformed structured responses', async () => {
  global.fetch = jest.fn().mockRejectedValue(new TypeError('Failed to fetch'));
  await expect(generateRecipe(request, new AbortController().signal)).rejects.toThrow('cannot reach the local server');
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => { throw new SyntaxError(); } });
  await expect(generateRecipe(request, new AbortController().signal)).rejects.toThrow('unreadable');
  for (const payload of [{ recipe: {} }, { ...generationFixture, recipe: { ...generationFixture.recipe, instructions: 'markdown' } },
    { ...generationFixture, recipe: { ...generationFixture.recipe, nutrition: { ...generationFixture.recipe.nutrition, calories: '500' } } }]) {
    expect(() => parseGenerationResponse(payload)).toThrow('invalid recipe');
  }
});

test('saving a generated ID twice is idempotent and retains unknown nutrition', () => {
  const recipe = toSavedRecipe(generationFixture.recipe);
  saveRecipe(recipe);
  saveRecipe(recipe);
  expect(readRecipes()).toHaveLength(1);
  expect(readRecipes()[0].structuredRecipe?.nutrition.sodium).toBeNull();
});

test('client deadline aborts the request and exposes a retry message', async () => {
  jest.useFakeTimers();
  global.fetch = jest.fn((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
  })) as jest.Mock;
  const promise = expect(generateRecipe(request, new AbortController().signal)).rejects.toThrow('took too long');
  jest.advanceTimersByTime(50001);
  await promise;
  expect(jest.getTimerCount()).toBe(0);
});

test('health timeout is bounded and never sends generation', async () => {
  jest.useFakeTimers();
  global.fetch = jest.fn((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
  })) as jest.Mock;
  const pending = expect(generateRecipe(request, new AbortController().signal)).rejects.toThrow('local server took too long');
  jest.advanceTimersByTime(5001);
  await pending;
  expect(global.fetch).toHaveBeenCalledTimes(1);
  expect(jest.getTimerCount()).toBe(0);
});
