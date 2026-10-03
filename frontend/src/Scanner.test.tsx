import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import IngredientScanner from './components/IngredientScanner';
import { AppContent } from './App';
import { AuthContext, AuthState } from './AuthContext';
import { analyzeIngredients } from './visionApi';
import { savePantry } from './pantryApi';

jest.mock('./visionApi', () => ({ analyzeIngredients: jest.fn() }));
jest.mock('./pantryApi', () => ({ savePantry: jest.fn() }));
const analyze = analyzeIngredients as jest.Mock;
const save = savePantry as jest.Mock;
const response = { analysis_id: 'test-analysis', warnings: [], provider: 'test', model: 'test', detections: [
  { display_name: 'broccoli', confidence: 'high', visible_state: null, uncertainty: '', normalized_name: 'broccoli', canonical_name: 'broccoli', identity_status: 'recognized' },
  { display_name: 'zucchini', confidence: 'medium', visible_state: null, uncertainty: 'Partly hidden', normalized_name: 'zucchini', canonical_name: 'zucchini', identity_status: 'recognized' },
  { display_name: 'mystery greens', confidence: 'low', visible_state: null, uncertainty: 'Unclear shape', normalized_name: 'mystery greens', canonical_name: null, identity_status: 'unresolved' },
] };
let auth: AuthState;
beforeEach(() => {
  jest.resetAllMocks();
  analyze.mockResolvedValue(response); save.mockResolvedValue({});
  URL.createObjectURL = jest.fn(() => 'blob:scanner'); URL.revokeObjectURL = jest.fn();
  window.scrollTo = jest.fn(); window.history.replaceState(null,'','/');
  auth = { user: { id: 'a' } as any, signedIn: true, accessToken: 'test', loading:false,error:'',recovering:false,
    signIn:jest.fn(),signUp:jest.fn(),signOut:jest.fn(),updatePassword:jest.fn() };
});
const wrap = (child: React.ReactNode) => <AuthContext.Provider value={auth}>{child}</AuthContext.Provider>;
const page = (create=jest.fn(), navigate=jest.fn()) => <IngredientScanner onNavigate={navigate} onCreateRecipe={create} />;
const upload = () => fireEvent.change(screen.getByLabelText('Upload Ingredient Photo'), { target: { files:[new File(['photo'],'test.png',{type:'image/png'})] } });
const detect = async () => { upload(); fireEvent.click(screen.getByRole('button',{name:'Analyze ingredients'})); await screen.findByRole('heading',{name:'Review ingredient suggestions'}); };
const confirm = () => fireEvent.click(screen.getByRole('button',{name:'Confirm ingredients'}));

test('selection previews locally and requires explicit analysis; no automatic writes', async () => {
  render(wrap(page())); upload();
  expect(screen.getByAltText('Ingredient preview')).toBeInTheDocument();
  expect(analyze).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Analyze ingredients'}));
  await screen.findByText('Looks like broccoli');
  expect(screen.getByText('Possibly zucchini')).toBeInTheDocument();
  expect(screen.getByText(/Not sure - please review mystery greens/)).toBeInTheDocument();
  expect(screen.getByText(/Name not matched yet/)).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Add to Pantry'})).not.toBeInTheDocument();
  expect(save).not.toHaveBeenCalled();
});

test('edit remove add and confirm preserve user corrections; no automatic action', async () => {
  const create=jest.fn(); render(wrap(page(create))); await detect();
  fireEvent.change(screen.getByLabelText('Ingredient 1'),{target:{value:'carrot'}});
  fireEvent.click(screen.getByRole('button',{name:'Remove ingredient 2'}));
  fireEvent.change(screen.getByLabelText('Missed ingredient'),{target:{value:'custom herb'}});
  fireEvent.click(screen.getByRole('button',{name:'Add ingredient'})); confirm();
  expect(create).not.toHaveBeenCalled(); expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Create recipe with these'}));
  expect(create).toHaveBeenCalledWith(['carrot','mystery greens','custom herb']);
});

test('editing confirmed list revokes confirmation', async () => {
  render(wrap(page())); await detect(); confirm();
  fireEvent.change(screen.getByLabelText('Ingredient 1'),{target:{value:'spinach'}});
  expect(screen.queryByRole('button',{name:'Add to Pantry'})).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Ingredient 1'),{target:{value:' '}});
  expect(screen.getByRole('button',{name:'Confirm ingredients'})).toBeDisabled();
});

test('authenticated Pantry saves only names with no inferred quantities', async () => {
  render(wrap(page())); await detect(); confirm();
  fireEvent.click(screen.getByRole('button',{name:'Add to Pantry'}));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(3));
  expect(save).toHaveBeenCalledWith('a',{name:'mystery greens',quantity:null,unit:null});
  await waitFor(() => expect(screen.getByRole('button',{name:'Add to Pantry'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Add to Pantry'}));
  expect(save).toHaveBeenCalledTimes(3);
});

test('partial Pantry failures and duplicate recovery do not repeat successful writes', async () => {
  save.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('This ingredient is already in your pantry.')).mockRejectedValueOnce(new Error('network'));
  render(wrap(page())); await detect(); confirm(); fireEvent.click(screen.getByRole('button',{name:'Add to Pantry'}));
  await screen.findByText(/Not added. Try again/);
  expect(screen.getByText('Already in Pantry')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Add to Pantry'}));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(4));
  expect(save.mock.calls[3][1].name).toBe('mystery greens');
});

test('signed-out analysis and confirmation work with sign-in guidance for Pantry', async () => {
  auth.user=null; auth.signedIn=false; const navigate=jest.fn(); const create=jest.fn();
  render(wrap(page(create,navigate))); await detect(); confirm();
  fireEvent.click(screen.getByRole('button',{name:'Add to Pantry'}));
  expect(screen.getByText(/Sign in to maintain/)).toBeInTheDocument(); expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Create recipe with these'})); expect(create).toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Sign in'})); expect(navigate).toHaveBeenCalledWith('profile');
});

test('loading prevents duplicate requests and allows cancellation', async () => {
  let resolve:any; analyze.mockImplementation(() => new Promise(r => {resolve=r;}));
  render(wrap(page())); upload(); fireEvent.click(screen.getByRole('button',{name:'Analyze ingredients'}));
  expect(screen.getByText('Looking for ingredients...')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Analyze ingredients'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Cancel analysis'}));
  expect(analyze.mock.calls[0][1].aborted).toBe(true);
  await act(async () => resolve(response));
  expect(screen.queryByText('Looks like broccoli')).not.toBeInTheDocument();
});

test('replace photo invalidates late results', async () => {
  let resolve:any; analyze.mockImplementationOnce(() => new Promise(r => {resolve=r;}));
  render(wrap(page())); upload(); fireEvent.click(screen.getByRole('button',{name:'Analyze ingredients'})); upload();
  await act(async () => resolve(response));
  expect(screen.queryByText('Looks like broccoli')).not.toBeInTheDocument();
  expect(analyze.mock.calls[0][1].aborted).toBe(true);
});

test('remove photo clears confirmed results and revokes URL', async () => {
  render(wrap(page())); await detect(); confirm(); fireEvent.click(screen.getByRole('button',{name:'Remove'}));
  expect(screen.queryByRole('heading',{name:'Confirmed ingredients'})).not.toBeInTheDocument();
  expect(screen.queryByAltText('Ingredient preview')).not.toBeInTheDocument(); expect(URL.revokeObjectURL).toHaveBeenCalled();
});

test('provider failure has no fake fallback and manual retry works', async () => {
  analyze.mockRejectedValueOnce(new Error('PRIVATE provider details'));
  render(wrap(page())); upload(); fireEvent.click(screen.getByRole('button',{name:'Analyze ingredients'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('could not complete');
  expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument(); expect(screen.queryByLabelText('Ingredient 1')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Analyze ingredients'})); await screen.findByText('Looks like broccoli');
  expect(analyze).toHaveBeenCalledTimes(2);
});

test('account switch stops queued Pantry writes and clears account-specific outcomes', async () => {
  let resolve:any; save.mockImplementationOnce(() => new Promise(r => {resolve=r;}));
  const view=render(wrap(page())); await detect(); confirm(); fireEvent.click(screen.getByRole('button',{name:'Add to Pantry'}));
  auth={...auth,user:{id:'b'} as any}; view.rerender(wrap(page()));
  await act(async () => resolve({}));
  expect(save).toHaveBeenCalledTimes(1); expect(screen.queryByText('Added to Pantry')).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Add to Pantry'})).not.toBeInTheDocument();
});

test('leaving Scanner aborts pending analysis', async () => {
  analyze.mockImplementation(() => new Promise(() => {})); const view=render(wrap(page())); upload();
  fireEvent.click(screen.getByRole('button',{name:'Analyze ingredients'})); view.unmount();
  expect(analyze.mock.calls[0][1].aborted).toBe(true);
});

test('empty detections allow manual review without inventing candidates', async () => {
  analyze.mockResolvedValue({...response,detections:[]}); render(wrap(page())); await detect();
  expect(screen.getByText(/No ingredients identified/)).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Confirm ingredients'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Missed ingredient'),{target:{value:'broccoli'}});
  fireEvent.click(screen.getByRole('button',{name:'Add ingredient'})); confirm();
  expect(screen.getByRole('heading',{name:'Confirmed ingredients'})).toBeInTheDocument();
});

test('App hands confirmed unresolved names to real Studio without generation', async () => {
  window.history.replaceState(null,'','/#scanner'); render(wrap(<AppContent />)); await detect(); confirm();
  fireEvent.click(screen.getByRole('button',{name:'Create recipe with these'}));
  expect(await screen.findByText('mystery greens')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Continue to Preferences'})).toBeEnabled();
  fireEvent.click(screen.getByRole('button',{name:'Continue to Preferences'}));
  expect(screen.getByRole('button',{name:/Create Recipe/})).toBeInTheDocument();
  expect(save).not.toHaveBeenCalled();
});
