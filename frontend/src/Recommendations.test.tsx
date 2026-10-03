import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import PantryRecommendations from './components/PantryRecommendations';
import Pantry from './components/Pantry';
import { getPantryRecommendations } from './recommendationApi';
import { AuthContext, AuthState } from './AuthContext';
import { generationFixture } from './recipeTestFixtures';
import { listPantry, savePantry } from './pantryApi';

jest.mock('./recommendationApi', () => ({ getPantryRecommendations: jest.fn() }));
jest.mock('./pantryApi', () => ({ listPantry: jest.fn(), savePantry: jest.fn(), deletePantry: jest.fn() }));
const get = getPantryRecommendations as jest.Mock;
let auth: AuthState;
const data = { state: 'ready', total: 2, skipped_count: 0, ineligible_count: 0, candidate_count: 2,
  entries: [1,2].map(i => ({ saved_recipe_id: String(i), recipe: { ...generationFixture.recipe, title: 'Real saved recipe ' + i },
    eligibility: 'eligible', rank: i, score: 60, reasons: [{ code: 'pantry', text: 'You have 2 of 3 listed ingredients.' }, { code: 'missing', text: 'Missing: lemon.' }] })) };
const wrap = (child: React.ReactNode) => <AuthContext.Provider value={auth}>{child}</AuthContext.Provider>;
beforeEach(() => {
  jest.resetAllMocks();
  auth = { user: { id: 'user-a' } as any, signedIn: true, accessToken: 'test', loading: false, error: '', recovering: false,
    signIn: jest.fn(), signUp: jest.fn(), signOut: jest.fn(), updatePassword: jest.fn() };
  get.mockResolvedValue(data);
});

test('loading then ranked order, reasons and View Recipe preserve real snapshot', async () => {
  let resolve: any; get.mockReturnValue(new Promise(r => { resolve=r; }));
  const open = jest.fn(); render(wrap(<PantryRecommendations revision={0} onOpenRecipe={open} />));
  expect(screen.getByRole('status')).toHaveTextContent('Finding pantry matches');
  await act(async () => { resolve(data); });
  expect(screen.getAllByRole('heading', { level: 3 }).map(x=>x.textContent)).toEqual(['Real saved recipe 1','Real saved recipe 2']);
  expect(screen.getAllByText('Missing: lemon.')).toHaveLength(2);
  fireEvent.click(screen.getAllByRole('button', { name: 'View Recipe' })[0]);
  expect(open).toHaveBeenCalledWith(data.entries[0].recipe);
});

test.each([
  ['empty_pantry','Add recognizable ingredients'],
  ['no_candidates','No saved recipes with ingredient details'],
  ['all_ineligible','None are recommended'],
  ['only_uncertain','checks remain uncertain'],
])('%s state is honest', async (state,text) => {
  get.mockResolvedValue({ ...data,state,entries:[],total:0 });
  render(wrap(<PantryRecommendations revision={0} />));
  expect(await screen.findByText(new RegExp(text))).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'View Recipe'})).not.toBeInTheDocument();
});

test('errors allow retry', async () => {
  get.mockRejectedValueOnce(new Error('Service unavailable'));
  render(wrap(<PantryRecommendations revision={0} />));
  expect(await screen.findByRole('alert')).toHaveTextContent('Service unavailable');
  fireEvent.click(screen.getByRole('button',{name:'Refresh matches'}));
  await screen.findByRole('heading',{name:'Real saved recipe 1'});
});

test('signed out sends no recommendation request', () => {
  auth.user=null;render(wrap(<PantryRecommendations revision={0} />));
  expect(get).not.toHaveBeenCalled();
});

test('account switch clears private candidates and ignores old response', async () => {
  let finish: any;get.mockReturnValueOnce(new Promise(r=>{finish=r;})).mockResolvedValue({ ...data, entries:[], state:'no_candidates' });
  const view=render(wrap(<PantryRecommendations revision={0} />));
  auth={...auth,user:{id:'user-b'} as any};view.rerender(wrap(<PantryRecommendations revision={0} />));
  await act(async()=>{finish(data);});
  expect(screen.queryByText('Real saved recipe 1')).not.toBeInTheDocument();
  expect(get).toHaveBeenLastCalledWith('user-b');
});

test('unknown candidates show review label and exclusions are counted', async () => {
  get.mockResolvedValue({...data,ineligible_count:1,entries:[{...data.entries[0],eligibility:'uncertain'}]});
  render(wrap(<PantryRecommendations revision={0} />));
  expect(await screen.findByText('Needs review')).toBeInTheDocument();
  expect(screen.getByText('1 incompatible recipes excluded.')).toBeInTheDocument();
});

test('pantry add refreshes recommendations without changing generation', async () => {
  (listPantry as jest.Mock).mockResolvedValue([]);
  (savePantry as jest.Mock).mockResolvedValue({id:'item',name:'salt',quantity:null,unit:null,identity_status:'recognized'});
  render(wrap(<Pantry onNavigate={jest.fn()} onOpenRecipe={jest.fn()} />));
  await screen.findByText(/Your pantry is empty/);
  await screen.findByRole('heading',{name:'Real saved recipe 1'});
  fireEvent.change(screen.getByLabelText('Ingredient name'),{target:{value:'salt'}});
  fireEvent.click(screen.getByRole('button',{name:'Add to pantry'}));
  await screen.findByText('Pantry saved.');
  await act(async()=>{});
  expect(get).toHaveBeenCalledTimes(2);
});
