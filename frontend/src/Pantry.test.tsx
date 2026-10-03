import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Pantry from './components/Pantry';
import RecipePantry from './components/RecipePantry';
import RecipeDetail from './components/RecipeDetail';
import { AuthContext, AuthState } from './AuthContext';
import { listPantry, savePantry, deletePantry, pantryCompatibility, PantryItem } from './pantryApi';
import { generationFixture } from './recipeTestFixtures';
import { AppContent } from './App';

jest.mock('./components/PantryRecommendations', () => () => null);
jest.mock('./pantryApi', () => ({ listPantry: jest.fn(), savePantry: jest.fn(), deletePantry: jest.fn(), pantryCompatibility: jest.fn() }));
const row: PantryItem = { id: 'item-a', name: 'Chicken Breasts', quantity: 2, unit: 'lb', normalized_name: 'chicken breast', food_state: null, identity_status: 'recognized', created_at: '2026-09-16', updated_at: '2026-09-16' };
let auth: AuthState;
const list = listPantry as jest.Mock;
const save = savePantry as jest.Mock;
const remove = deletePantry as jest.Mock;
const coverage = pantryCompatibility as jest.Mock;
const compatibility = { pantry_count: 1, usable_pantry_count: 1, ingredient_count: 3, available_count: 1, missing_count: 1, unknown_count: 1, coverage_percent: 33.3,
  ingredients: [{ ingredient_index: 0, name: 'chicken breast', status: 'available' }, { ingredient_index: 1, name: 'broccoli', status: 'missing' }, { ingredient_index: 2, name: 'special blend', status: 'unknown' }] };
beforeEach(() => {
  jest.resetAllMocks();
  auth = { user: { id: 'user-a' } as any, signedIn: true, accessToken: 'test-only', loading: false, error: '', recovering: false,
    signIn: jest.fn(), signUp: jest.fn(), signOut: jest.fn(), updatePassword: jest.fn() };
  list.mockResolvedValue([]); save.mockResolvedValue(row); remove.mockResolvedValue(undefined); coverage.mockResolvedValue(compatibility);
  window.scrollTo = jest.fn(); window.history.replaceState(null, '', '/');
});
const wrap = (child: React.ReactNode) => <AuthContext.Provider value={auth}>{child}</AuthContext.Provider>;
const page = () => <Pantry onNavigate={jest.fn()} />;

test('typeahead selects canonical name and preserves entered quantity and unit', async () => {
  render(wrap(page())); await screen.findByText(/Your pantry is empty/);
  fireEvent.change(screen.getByLabelText('Quantity (optional)'), {target:{value:'250'}});
  fireEvent.change(screen.getByLabelText('Unit (optional)'), {target:{value:'g'}});
  fireEvent.change(screen.getByLabelText('Ingredient name'), {target:{value:'rajma'}});
  fireEvent.click(screen.getByRole('option',{name:'Kidney beans'}));
  fireEvent.click(screen.getByRole('button',{name:'Add to pantry'}));
  await waitFor(()=>expect(save).toHaveBeenCalledWith('user-a',{name:'Kidney beans',quantity:250,unit:'g'},undefined));
});

test('custom name and explicitly typed state are submitted without substitution', async () => {
  render(wrap(page())); await screen.findByText(/Your pantry is empty/);
  fireEvent.change(screen.getByLabelText('Ingredient name'), {target:{value:'raw regional vegetable'}});
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Add to pantry'}));
  await waitFor(()=>expect(save).toHaveBeenCalledWith('user-a',{name:'raw regional vegetable',quantity:null,unit:null},undefined));
});

test('related chicken stays in Unknown while exact and absent ingredients use their own groups', async () => {
  coverage.mockResolvedValue({...compatibility,ingredients:[
    {ingredient_index:0,name:'raw chicken breast',status:'unknown'},
    {ingredient_index:1,name:'raw broccoli',status:'available'},
    {ingredient_index:2,name:'carrot',status:'missing'}]});
  render(wrap(<RecipePantry recipe={generationFixture.recipe} />));
  await screen.findByText('raw chicken breast');
  expect(screen.getByText('raw chicken breast').parentElement?.parentElement).toHaveTextContent('Unknown / check manually');
  expect(screen.getByText('raw broccoli').parentElement?.parentElement).toHaveTextContent('Have');
  expect(screen.getByText('carrot').parentElement?.parentElement).toHaveTextContent('Missing');
});

test('signed-out pantry explains account requirement without cloud calls', () => {
  auth.user = null; auth.signedIn = false;
  const navigate = jest.fn(); render(wrap(<Pantry onNavigate={navigate} />));
  expect(screen.getByText(/Sign in to maintain/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(navigate).toHaveBeenCalledWith('profile'); expect(list).not.toHaveBeenCalled();
});
test('loading resolves to useful empty state', async () => {
  let finish: any; list.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(wrap(page())); expect(screen.getByRole('status')).toHaveTextContent('Loading pantry');
  await act(async () => { finish([]); }); expect(screen.getByText(/Your pantry is empty/)).toBeInTheDocument();
});
test('adds name with optional quantity and unit through owner-scoped API', async () => {
  render(wrap(page())); await screen.findByText(/Your pantry is empty/);
  fireEvent.change(screen.getByLabelText('Ingredient name'), { target: { value: 'Chicken Breasts' } });
  fireEvent.change(screen.getByLabelText('Quantity (optional)'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('Unit (optional)'), { target: { value: 'lb' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add to pantry' }));
  await screen.findByRole('heading', { name: row.name });
  expect(save).toHaveBeenCalledWith('user-a', { name: row.name, quantity: 2, unit: 'lb' }, undefined);
});
test('blank quantity and unit remain unknown', async () => {
  render(wrap(page())); await screen.findByText(/Your pantry is empty/);
  fireEvent.change(screen.getByLabelText('Ingredient name'), { target: { value: 'salt' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add to pantry' }));
  await waitFor(() => expect(save).toHaveBeenCalledWith('user-a', { name: 'salt', quantity: null, unit: null }, undefined));
});
test('edits populated pantry without merging quantities', async () => {
  list.mockResolvedValue([row]); save.mockResolvedValue({ ...row, quantity: 4 });
  render(wrap(page())); fireEvent.click(await screen.findByRole('button', { name: 'Edit Chicken Breasts' }));
  fireEvent.change(screen.getByLabelText('Quantity (optional)'), { target: { value: '4' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByText('4 lb');
  expect(save).toHaveBeenCalledWith('user-a', { name: row.name, quantity: 4, unit: 'lb' }, row.id);
});
test('delete removes the item only after success', async () => {
  list.mockResolvedValue([row]); render(wrap(page()));
  fireEvent.click(await screen.findByRole('button', { name: 'Delete Chicken Breasts' }));
  await screen.findByText(/Your pantry is empty/); expect(remove).toHaveBeenCalledWith('user-a', row.id);
});
test('failed delete preserves item and exposes recovery', async () => {
  list.mockResolvedValue([row]); remove.mockRejectedValue(new Error('Account storage unavailable.'));
  render(wrap(page())); fireEvent.click(await screen.findByRole('button', { name: 'Delete Chicken Breasts' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Account storage unavailable');
  expect(screen.getByRole('heading', { name: row.name })).toBeInTheDocument();
});
test('duplicate error retains user input and existing item', async () => {
  list.mockResolvedValue([row]); save.mockRejectedValue(new Error('This ingredient is already in your pantry. Edit the existing item instead.'));
  render(wrap(page())); await screen.findByRole('heading', { name: row.name });
  fireEvent.change(screen.getByLabelText('Ingredient name'), { target: { value: 'chicken breast' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add to pantry' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('already in your pantry');
  expect(screen.getByLabelText('Ingredient name')).toHaveValue('chicken breast');
  expect(screen.getAllByRole('button', { name: 'Edit Chicken Breasts' })).toHaveLength(1);
});
test('failed list can be refreshed', async () => {
  list.mockRejectedValueOnce(new Error('Account storage unavailable.')).mockResolvedValueOnce([row]);
  render(wrap(page())); await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', { name: 'Refresh pantry' }));
  await screen.findByRole('heading', { name: row.name }); expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
test('account switch clears pantry and ignores late old-account responses', async () => {
  let finish: any; list.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValue([]);
  const view = render(wrap(page()));
  auth = { ...auth, user: { id: 'user-b' } as any }; view.rerender(wrap(page()));
  await screen.findByText(/Your pantry is empty/);
  await act(async () => { finish([row]); });
  expect(screen.queryByRole('heading', { name: row.name })).not.toBeInTheDocument();
});
test('signout clears visible pantry', async () => {
  list.mockResolvedValue([row]); const view = render(wrap(page())); await screen.findByRole('heading', { name: row.name });
  auth = { ...auth, user: null, signedIn: false }; view.rerender(wrap(page()));
  expect(screen.queryByRole('heading', { name: row.name })).not.toBeInTheDocument();
});
test('compatibility displays concise available missing and unknown information', async () => {
  render(wrap(<RecipePantry recipe={generationFixture.recipe} />));
  expect(await screen.findByRole('region', { name: 'Pantry compatibility' })).toHaveTextContent('1 / 3 ingredients available by name');
  expect(screen.getByText('Unknown / check manually')).toBeInTheDocument();
  expect(screen.getByText('special blend')).toBeInTheDocument();
  expect(coverage).toHaveBeenCalledWith('user-a', generationFixture.recipe.ingredients);
});
test('signed-out and empty pantry show no misleading coverage', async () => {
  auth.user = null; const view = render(wrap(<RecipePantry recipe={generationFixture.recipe} />));
  expect(coverage).not.toHaveBeenCalled();
  auth = { ...auth, user: { id: 'user-a' } as any }; coverage.mockResolvedValue({ ...compatibility, pantry_count: 0, usable_pantry_count: 0, coverage_percent: null });
  view.rerender(wrap(<RecipePantry recipe={generationFixture.recipe} />)); await act(async () => {});
  expect(screen.queryByRole('region')).not.toBeInTheDocument();
});
test('compatibility errors can be retried without changing recipe', async () => {
  coverage.mockRejectedValueOnce(new Error('failure')).mockResolvedValueOnce(compatibility);
  render(wrap(<RecipePantry recipe={generationFixture.recipe} />));
  fireEvent.click(await screen.findByRole('button', { name: 'Retry pantry check' }));
  await screen.findByRole('region', { name: 'Pantry compatibility' });
});
test('compatibility does not show prior account or recipe responses', async () => {
  let finish: any; coverage.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValue({ ...compatibility, pantry_count: 0, usable_pantry_count: 0 });
  const view = render(wrap(<RecipePantry recipe={generationFixture.recipe} />));
  auth = { ...auth, user: { id: 'user-b' } as any }; view.rerender(wrap(<RecipePantry recipe={generationFixture.recipe} />));
  await act(async () => { finish(compatibility); }); expect(screen.queryByRole('region')).not.toBeInTheDocument();
});
test('pantry is reachable in existing navigation', async () => {
  render(wrap(<AppContent />));
  fireEvent.click(screen.getAllByRole('button', { name: /Pantry/ })[0]);
  await screen.findByRole('heading', { name: 'Pantry' });
  await screen.findByText(/Your pantry is empty/);
  expect(list).toHaveBeenCalledWith('user-a');
});


test('real Recipe Detail connects pantry coverage without replacing recipe intelligence', async () => {
  render(wrap(<RecipeDetail generatedRecipe={generationFixture.recipe} onNavigate={jest.fn()} />));
  expect(await screen.findByRole('region', { name: 'Pantry compatibility' })).toHaveTextContent('1 / 3');
  expect(screen.getByRole('heading', { name: 'Nutrition per serving' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Instructions' })).toBeInTheDocument();
  expect(screen.getByText('broccoli')).toBeInTheDocument();
  expect(screen.getByText('special blend')).toBeInTheDocument();
});

test('pantry containing only unresolved identities does not display coverage', async () => {
  coverage.mockResolvedValue({ ...compatibility, usable_pantry_count: 0, coverage_percent: null });
  render(wrap(<RecipePantry recipe={generationFixture.recipe} />));
  await act(async () => {});
  expect(screen.queryByRole('region', { name: 'Pantry compatibility' })).not.toBeInTheDocument();
});
