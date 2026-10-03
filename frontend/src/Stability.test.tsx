import { testAccount } from './accountTestFixtures';
import { generationFixture, mockGenerationFetch } from './recipeTestFixtures';
import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import App from './App';
import IngredientScanner from './components/IngredientScanner';
import MealAnalyzer from './components/MealAnalyzer';
import RecipeGenerator from './components/RecipeGenerator';
import RecipeResults from './components/RecipeResults';
import RecipeDetail from './components/RecipeDetail';
import Profile from './components/Profile';
import SavedRecipes from './components/SavedRecipes';
import { saveRecipe } from './recipeStorage';

let errors: jest.SpyInstance;
let warnings: jest.SpyInstance;
beforeEach(() => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 });
  mockGenerationFetch();
  localStorage.clear();
  window.history.replaceState(null, '', '/');
  window.scrollTo = jest.fn();
  jest.spyOn(window, 'alert').mockImplementation(() => {});
  errors = jest.spyOn(console, 'error').mockImplementation(() => {});
  warnings = jest.spyOn(console, 'warn').mockImplementation(() => {});
  URL.createObjectURL = jest.fn().mockReturnValue('blob:test-image');
  URL.revokeObjectURL = jest.fn();
});
afterEach(() => {
  cleanup();
  const messages = [...errors.mock.calls, ...warnings.mock.calls];
  jest.useRealTimers();
  jest.restoreAllMocks();
  expect(messages).toEqual([]);
});

test.each(['home', 'generator', 'results', 'detail', 'scanner', 'analyzer', 'saved', 'discover', 'profile', 'unknown'])('%s route renders without React errors', route => {
  window.history.replaceState(null, '', `/#${route}`);
  render(<React.StrictMode><App /></React.StrictMode>);
  expect(screen.getAllByRole('heading').length).toBeGreaterThan(0);
  expect(screen.getByRole('main')).not.toBeEmptyDOMElement();
  expect(document.title).toContain(route === 'unknown' ? 'Home' : route[0].toUpperCase() + route.slice(1));
});

test('floating navigation destinations render at mobile width', () => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 375 });
  render(<App />);
  for (const label of ['Home','Pantry','Studio','Scanner','Analyzer','Saved']) {
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: label }));
    expect(screen.getAllByRole('heading').length).toBeGreaterThan(0);
  }
});

test('header home action and hash navigation work', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Create a recipe' }));
  expect(screen.getByRole('searchbox')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'MealMind home' }));
  expect(screen.getByRole('heading', { name: 'Welcome to your kitchen' })).toBeInTheDocument();
  act(() => { window.history.replaceState(null, '', '/#scanner'); window.dispatchEvent(new HashChangeEvent('hashchange')); });
  expect(screen.getByRole('heading', { name: 'Scan ingredients' })).toBeInTheDocument();
});

test('generator search, duplicate selection, removal, reset, all preferences and API generation', async () => {
  jest.useFakeTimers();
  const view = render(<RecipeGenerator onNavigate={jest.fn()} />);
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'missing ingredient' } });
  expect(screen.getByText(/No ingredients found/)).toBeInTheDocument();
  for (let i = 0; i < 2; i++) {
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '  lentil  ' } });
    fireEvent.click(within(screen.getByLabelText('Ingredient search results')).getByRole('button', { name: 'Lentils' }));
  }
  expect(screen.getByText('Selected Ingredients (0)')).toBeInTheDocument();
  fireEvent.click(within(screen.getByLabelText('Ingredient search results')).getByRole('button', { name: 'Lentils' }));
  expect(screen.getByText('Selected Ingredients (1)')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Remove Lentils' }));
  expect(screen.getByRole('button', { name: 'Select Ingredients' })).toBeDisabled();
  fireEvent.click(screen.getAllByRole('button', { name: 'Tofu' })[0]);
  fireEvent.click(screen.getByRole('button', { name: /Clear All/ }));
  expect(screen.getByRole('button', { name: 'Select Ingredients' })).toBeDisabled();
  fireEvent.click(screen.getAllByRole('button', { name: 'Tofu' })[0]);
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
  screen.getAllByRole('spinbutton').forEach(input => fireEvent.change(input, { target: { value: '2' } }));
  screen.getAllByRole('combobox').forEach(input => {
    const select = input as HTMLSelectElement;
    fireEvent.change(select, { target: { value: select.options[1].value } });
    expect(select.value).toBe(select.options[1].value);
  });
  screen.getAllByRole('checkbox').forEach(input => { fireEvent.click(input); expect(input).toBeChecked(); fireEvent.click(input); expect(input).not.toBeChecked(); });
  fireEvent.click(screen.getByRole('button', { name: /Create Recipe/ }));
  expect(screen.getByRole('button', { name: /Generating Recipe/ })).toBeDisabled();
  await act(async () => { jest.advanceTimersByTime(2100); });
  expect(screen.getByText('Lentil and Tomato Stew')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Start Over/ }));
  expect(screen.getByRole('button', { name: 'Select Ingredients' })).toBeDisabled();
  view.unmount();
});

test.each([
  { Component: IngredientScanner, label: 'Upload Ingredient Photo', preview: 'Ingredient preview' },
  { Component: MealAnalyzer, label: 'Upload Meal Photo', preview: 'Meal preview' },
])('$label validates and previews photos without fabricating AI results', ({ Component, label, preview }) => {
  const navigate = jest.fn(); const view = render(<Component onNavigate={navigate} />);
  const input = screen.getByLabelText(label);
  const upload = (file: File) => fireEvent.change(input, { target: { files: [file] } });
  upload(new File(['bad'], 'bad.txt', { type: 'text/plain' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Please upload a valid image file');
  const oversized = new File(['image'], 'large.png', { type: 'image/png' });
  Object.defineProperty(oversized, 'size', { value: 6 * 1024 * 1024 }); upload(oversized);
  expect(screen.getByRole('alert')).toHaveTextContent('Image file too large');
  const photo = new File(['image'], 'meal.png', { type: 'image/png' }); upload(photo);
  expect(screen.getByRole('img', { name: preview })).toHaveAttribute('src', 'blob:test-image');
  expect(screen.getByText(/Photos are sent to Gemini through MealMind/)).toBeInTheDocument();
  expect(global.fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
  expect(screen.queryByRole('img', { name: preview })).not.toBeInTheDocument();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-image');
  fireEvent.drop(input.parentElement!, { dataTransfer: { files: [photo] } });
  expect(screen.getByRole('img', { name: preview })).toBeInTheDocument();
  if (preview === 'Ingredient preview') {
    fireEvent.click(screen.getByRole('button', { name: 'Enter ingredients in Recipe Studio' }));
    expect(navigate).toHaveBeenCalledWith('generator');
  } else expect(screen.queryByRole('button', { name: 'Enter ingredients in Recipe Studio' })).not.toBeInTheDocument();
  view.unmount(); expect(URL.revokeObjectURL).toHaveBeenCalled();
});

test('leaving preferences cancels generation; zero values and save-error recovery work', async () => {
  jest.useFakeTimers();
  mockGenerationFetch({ ...generationFixture, recipe: { ...generationFixture.recipe, nutrition: { calories: 0, protein: 0, carbohydrates: 0, fat: 0, fiber: null, sodium: null } } });
  const account = testAccount();
  const view = render(<account.Provider><RecipeGenerator onNavigate={jest.fn()} /></account.Provider>);
  fireEvent.click(screen.getAllByRole('button', { name: 'Tofu' })[0]);
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
  fireEvent.click(screen.getByRole('button', { name: /Create Recipe/ }));
  fireEvent.click(screen.getByRole('button', { name: /Back to Ingredients/ }));
  await act(async () => { jest.advanceTimersByTime(2100); });
  expect(screen.getByRole('searchbox')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
  screen.getAllByRole('spinbutton').slice(0, 4).forEach(input => fireEvent.change(input, { target: { value: '0' } }));
  const servings = screen.getByPlaceholderText('e.g., 4');
  fireEvent.change(servings, { target: { value: '-1' } });
  expect(servings).toBeInvalid();
  fireEvent.change(servings, { target: { value: '2' } });
  expect(servings).toBeValid();
  fireEvent.click(screen.getByRole('button', { name: /Create Recipe/ }));
  await act(async () => { jest.advanceTimersByTime(2100); });
  account.store.failSave = true;
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save Recipe' })); });
  expect(screen.getByRole('alert')).toHaveTextContent('Account storage is unavailable');
  account.store.failSave = false;
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save Recipe' })); });
  expect(account.store.rows[0].recipe.nutrition).toEqual({ calories: 0, protein: 0, carbs: 0, fat: 0 });
  fireEvent.click(screen.getByRole('button', { name: /Start Over/ }));
  fireEvent.click(screen.getAllByRole('button', { name: 'Tofu' })[0]);
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
  fireEvent.click(screen.getByRole('button', { name: /Create Recipe/ }));
  view.unmount();
  await act(async () => {});
  expect((global.fetch as jest.Mock).mock.calls.slice(-1)[0][1].signal.aborted).toBe(true);
});

test('results and detail show honest empty states without sample recipes', () => {
  const view = render(<RecipeResults onNavigate={jest.fn()} />);
  expect(screen.getByText(/No generated recipe yet/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save recipe' })).not.toBeInTheDocument(); view.unmount();
  render(<RecipeDetail onNavigate={jest.fn()} />);
  expect(screen.getByText(/Open a saved recipe or generate one/)).toBeInTheDocument();
});

test('structured detail checklist works with real recipe data', () => {
  render(<RecipeDetail generatedRecipe={generationFixture.recipe} onNavigate={jest.fn()} />);
  screen.getAllByRole('checkbox').forEach(input => { fireEvent.click(input); expect(input).toBeChecked(); });
  expect(screen.getByText(generationFixture.recipe.instructions[0])).toBeInTheDocument();
});

test('profile checkboxes work and cancelling edits restores the saved profile', async () => {
  const account = testAccount();
  render(<account.Provider><Profile onNavigate={jest.fn()} /></account.Provider>);
  screen.getAllByRole('checkbox').forEach(input => { const checked = (input as HTMLInputElement).checked; fireEvent.click(input); expect((input as HTMLInputElement).checked).toBe(!checked); });
  fireEvent.click(screen.getByRole('button', { name: 'Edit Profile' }));
  fireEvent.change(screen.getByPlaceholderText('Enter your name'), { target: { value: 'Unsaved name' } });
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByRole('heading', { name: 'Test User' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Edit Profile' }));
  fireEvent.change(screen.getByPlaceholderText('Enter your name'), { target: { value: 'Audit User' } });
  expect(screen.getByLabelText('Account email')).toHaveAttribute('readonly');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save Changes' })); });
  expect(screen.getByRole('heading', { name: 'Audit User' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Sign Out' }));
  expect(account.auth.signOut).toHaveBeenCalled();
});

test('saved collection sorts, expands and handles unavailable storage without crashing', () => {
  const recipe = { name: 'Z recipe', ingredients: ['Tofu'], instructions: 'Mock instructions', prepTime: '5 mins', cookTime: '10 mins', servings: 2, difficulty: 'Easy', nutrition: { calories: 200, protein: 20, carbs: 10, fat: 5 } };
  saveRecipe(recipe); saveRecipe({ ...recipe, name: 'A recipe' });
  render(<SavedRecipes onNavigate={jest.fn()} />);
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'name' } });
  expect(screen.getAllByRole('heading', { level: 2 }).map(item => item.textContent)).toEqual(['A recipe', 'Z recipe']);
  fireEvent.click(screen.getAllByRole('button', { name: 'View details' })[0]);
  fireEvent.click(screen.getByRole('button', { name: 'Hide details' }));
  jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Quota exceeded'); });
  fireEvent.click(screen.getByRole('button', { name: 'Remove A recipe' }));
  expect(screen.getByRole('alert')).toHaveTextContent('could not be removed');
  expect(screen.getByRole('heading', { name: 'A recipe' })).toBeInTheDocument();
});


test('compact ingredient categories preserve selection, exclusions and progression', () => {
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  const categories = screen.getByLabelText('Ingredient categories');
  within(categories).getAllByRole('button').forEach(button => expect(button).toHaveAttribute('aria-expanded', 'false'));
  expect(screen.queryByRole('button', { name: 'Honey' })).not.toBeInTheDocument();
  fireEvent.click(within(categories).getByRole('button', { name: 'Sweeteners' }));
  expect(within(categories).getByRole('button', { name: 'Sweeteners' })).toHaveAttribute('aria-expanded', 'true');
  fireEvent.click(screen.getByRole('button', { name: 'Honey' }));
  expect(screen.getByRole('button', { name: 'Remove Honey' })).toBeInTheDocument();
  fireEvent.click(within(categories).getByRole('button', { name: 'Vegetables' }));
  expect(screen.queryByRole('group', { name: 'Sweeteners ingredients' })).not.toBeInTheDocument();
  fireEvent.click(within(screen.getByRole('group', { name: 'Vegetables ingredients' })).getByRole('button', { name: 'Carrots' }));
  fireEvent.click(within(categories).getByRole('button', { name: 'Vegetables' }));
  expect(screen.queryByRole('group', { name: 'Vegetables ingredients' })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Excluded ingredients (comma-separated)'), { target: { value: 'mushrooms' } });
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
  fireEvent.click(screen.getByRole('button', { name: /Back to Ingredients/ }));
  expect(screen.getByLabelText('Excluded ingredients (comma-separated)')).toHaveValue('mushrooms');
  expect(screen.getByRole('button', { name: 'Remove Honey' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Remove Carrots' })).toBeInTheDocument();
});

test.each([['ingredient', IngredientScanner], ['meal', MealAnalyzer]] as const)('%s styled picker opens the real file input', (kind, Component) => {
  render(<Component onNavigate={jest.fn()} />);
  const input = screen.getByLabelText(kind === 'ingredient' ? 'Upload Ingredient Photo' : 'Upload Meal Photo');
  const click = jest.spyOn(input, 'click');
  fireEvent.click(screen.getByRole('button', { name: 'Choose a photo' }));
  expect(click).toHaveBeenCalledTimes(1);
  expect(input).toHaveAttribute('type', 'file');
  expect(input).not.toHaveAttribute('aria-hidden');
  expect(input).not.toHaveAttribute('tabindex', '-1');
});
