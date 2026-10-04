import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';
import { UserDataProvider, useUserData } from './UserDataContext';
import { supabase, isRecoverySession } from './supabase';
import { accountRequest, emptyPreferences, UserPreferences } from './accountApi';
import { importLegacy, pendingImports } from './legacyImport';
import { saveRecipe, readRecipes } from './recipeStorage';
import { generationFixture } from './recipeTestFixtures';
import { toSavedRecipe } from './recipeApi';
import AuthPanel from './components/AuthPanel';
import Profile from './components/Profile';
import SavedRecipes from './components/SavedRecipes';
import RecipeDetail from './components/RecipeDetail';
import RecipeGenerator from './components/RecipeGenerator';
import { AppContent } from './App';
import { within } from '@testing-library/react';

jest.mock('./supabase', () => ({ isRecoverySession: jest.fn(() => false), completeRecovery: jest.fn(), supabase: { auth: { getSession: jest.fn(), onAuthStateChange: jest.fn(), signInWithPassword: jest.fn(), signUp: jest.fn(), signOut: jest.fn(), updateUser: jest.fn() } } }));
const auth = supabase!.auth as any;
const user = { id: 'user-a', email: 'a@example.com' };
let session: any;
let listener: (event: string, value: any) => void;
let rows: any[];
let preferences: UserPreferences;
const snapshot = { ...toSavedRecipe(generationFixture.recipe), savedAt: '2026-09-14' };
const json = (data: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => JSON.parse(JSON.stringify(data)) });
beforeEach(() => {
  localStorage.clear(); rows = []; preferences = JSON.parse(JSON.stringify(emptyPreferences)); session = null;
  jest.clearAllMocks();
  auth.getSession.mockImplementation(async () => ({ data: { session }, error: null }));
  auth.onAuthStateChange.mockImplementation((callback: any) => { listener = callback; return { data: { subscription: { unsubscribe: jest.fn() } } }; });
  auth.signInWithPassword.mockImplementation(async () => { session = { user, access_token: 'verified-token' }; listener?.('SIGNED_IN', session); return { data: { session }, error: null }; });
  auth.signUp.mockResolvedValue({ data: { session: null }, error: null });
  auth.signOut.mockImplementation(async () => { session = null; listener?.('SIGNED_OUT', null); return { error: null }; });
  global.fetch = jest.fn(async (url, options: any = {}) => {
    const path = new URL(String(url)).pathname;
    if (path === '/api/preferences') {
      if (options.method === 'PUT') preferences = JSON.parse(options.body);
      return json(preferences);
    }
    if (path === '/api/profile') return json({ display_name: 'Account User' });
    if (path === '/api/saved-recipes') {
      if (options.method === 'POST') {
        const body = JSON.parse(options.body);
        let row = rows.find(r => r.source_id === body.source_id);
        if (!row) { row = { ...body, id: `row-${rows.length}`, created_at: '2026-09-14' }; rows.push(row); }
        return json(row);
      }
      return json(rows);
    }
    if (options.method === 'DELETE') { rows = rows.filter(r => !path.endsWith(r.id)); return json(null, 204); }
    throw new Error('Unexpected test request');
  }) as jest.Mock;
});
const signedIn = () => { session = { user, access_token: 'verified-token' }; };

test('saved Profile preferences reload into authenticated generation', async () => {
  signedIn();
  const view=render(<Providers><Profile onNavigate={jest.fn()} /></Providers>);
  await screen.findByRole('heading',{name:'Account User'});
  fireEvent.click(screen.getByLabelText('Vegetarian'));
  fireEvent.change(screen.getByLabelText('Excluded ingredients (comma-separated)'),{target:{value:'mushrooms'}});
  fireEvent.change(screen.getByLabelText('Preferred cuisines (comma-separated)'),{target:{value:'indian'}});
  fireEvent.change(screen.getByLabelText('Maximum calories (kcal)'),{target:{value:'600'}});
  fireEvent.click(screen.getByRole('button',{name:'Save preferences'}));
  await screen.findByText('Profile and preferences saved.');view.unmount();
  const accountFetch=global.fetch;
  let sent:any;
  global.fetch=jest.fn(async (url,options:any={}) => {
    if(String(url).endsWith('/health')) return json({status:'ok'}) as any;
    if(String(url).endsWith('/api/recipes/generate')) {sent=options;return json(generationFixture) as any;}
    return accountFetch(url,options);
  });
  render(<Providers><RecipeGenerator onNavigate={jest.fn()} /></Providers>);
  fireEvent.click(screen.getByRole('button',{name:'Broccoli'}));
  fireEvent.click(screen.getByRole('button',{name:'Continue to Preferences'}));
  await waitFor(()=>expect(screen.getByLabelText('Target Calories (per serving)')).toHaveValue(600));
  fireEvent.click(screen.getByRole('button',{name:'Create Recipe'}));
  await screen.findByRole('heading',{name:generationFixture.recipe.title});
  expect(sent.headers.Authorization).toBe('Bearer verified-token');
  expect(JSON.parse(sent.body)).toMatchObject({dietary_preferences:['vegetarian'],excluded_ingredients:['mushrooms'],cuisine:'indian',calorie_target:600});
});
function Providers({ children }: { children: React.ReactNode }) { return <AuthProvider><UserDataProvider>{children}</UserDataProvider></AuthProvider>; }
function Probe() {
  const state = useAuth(); const data = useUserData();
  return <><p>{state.loading ? 'Restoring' : state.signedIn ? state.user!.email : 'Signed out'}</p>
    <p>{state.loading || data.loading ? 'Data loading' : 'Data ready'}</p><p>{state.error || data.error}</p>
    <button onClick={() => void state.signIn('a@example.com', 'password')}>Login probe</button>
    <button onClick={() => void state.signOut()}>Logout probe</button></>;
}

test('restores session, signs in and signs out, clearing account data', async () => {
  render(<Providers><Probe /></Providers>);
  await screen.findByText('Signed out');
  fireEvent.click(screen.getByText('Login probe'));
  await screen.findByText('a@example.com');
  await screen.findByText('Data ready');
  fireEvent.click(screen.getByText('Logout probe'));
  await screen.findByText('Signed out');
});

test('sign up without a session explains email confirmation', async () => {
  render(<AuthProvider><AuthPanel /></AuthProvider>);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Sign In' })).toBeEnabled());
  fireEvent.click(screen.getByText('Create an account'));
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password123' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign Up' }));
  await screen.findByText(/Check your email to confirm/);
  expect(auth.signUp).toHaveBeenCalledWith({ email: 'new@example.com', password: 'password123' });
});

test('central client attaches current access token and rejects account changes', async () => {
  signedIn(); await accountRequest('/api/preferences');
  expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/preferences'), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer verified-token' }) }));
  await expect(accountRequest('/api/preferences', 'PUT', {}, 'other-user')).rejects.toThrow('account changed');
  expect(global.fetch).toHaveBeenCalledTimes(1);
});

test('signed-out Save explains sign-in and never writes local or cloud data', async () => {
  render(<RecipeDetail generatedRecipe={generationFixture.recipe} onNavigate={jest.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Save recipe' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Sign in to save');
  expect(readRecipes()).toEqual([]); expect(global.fetch).not.toHaveBeenCalled();
});

test('authenticated save, reopen from backend, and delete preserve structured metadata', async () => {
  signedIn();
  const view = render(<Providers><Probe /><RecipeDetail generatedRecipe={generationFixture.recipe} onNavigate={jest.fn()} /></Providers>);
  await screen.findByText('Data ready');
  fireEvent.click(screen.getByRole('button', { name: 'Save recipe' }));
  await screen.findByRole('button', { name: 'Remove from saved recipes' });
  expect(rows[0].recipe.structuredRecipe).toEqual(generationFixture.recipe);
  expect(readRecipes()).toEqual([]);
  view.unmount();
  const open = jest.fn();
  render(<Providers><SavedRecipes onNavigate={jest.fn()} onOpenRecipe={open} /></Providers>);
  await screen.findByRole('heading', { name: generationFixture.recipe.title });
  fireEvent.click(screen.getByRole('button', { name: 'Open full recipe' }));
  expect(open).toHaveBeenCalledWith(generationFixture.recipe);
  fireEvent.click(screen.getByRole('button', { name: `Remove ${generationFixture.recipe.title}` }));
  await waitFor(() => expect(rows).toHaveLength(0));
});

test('Profile preferences persist across remount with existing semantics', async () => {
  signedIn();
  const view = render(<Providers><Profile onNavigate={jest.fn()} /></Providers>);
  await screen.findByRole('heading', { name: 'Account User' });
  fireEvent.click(screen.getByLabelText('Vegan'));
  fireEvent.click(screen.getByLabelText('Nut Allergy'));
  fireEvent.change(screen.getByLabelText('Maximum calories (kcal)'), { target: { value: '0' } });
  fireEvent.change(screen.getByLabelText('Preferred cuisines (comma-separated)'), { target: { value: 'Italian' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save preferences' }));
  await screen.findByText('Profile and preferences saved.');
  expect(preferences).toMatchObject({ dietary_preferences: ['vegan'], allergies: ['nuts'], nutrition_targets: { calorie_target: 0 }, preferred_cuisines: ['Italian'] });
  view.unmount();
  render(<Providers><Profile onNavigate={jest.fn()} /></Providers>);
  await waitFor(() => expect(screen.getByLabelText('Vegan')).toBeChecked());
  expect(screen.getByLabelText('Maximum calories (kcal)')).toHaveValue(0);
});

test('legacy import is explicit, preserves local data, and is offered only once per account', async () => {
  signedIn(); saveRecipe(snapshot);
  const view = render(<Providers><SavedRecipes onNavigate={jest.fn()} /></Providers>);
  fireEvent.click(await screen.findByRole('button', { name: 'Import local recipes' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Import local recipes' })).not.toBeInTheDocument());
  expect(rows).toHaveLength(1); expect(readRecipes()).toHaveLength(1);
  view.unmount();
  render(<Providers><SavedRecipes onNavigate={jest.fn()} /></Providers>);
  await screen.findByRole('heading', { name: snapshot.name });
  expect(screen.queryByRole('button', { name: 'Import local recipes' })).not.toBeInTheDocument();
});

test('failed import retains local data and resumes only incomplete items', async () => {
  const local = [snapshot, { ...snapshot, id: 'second' }];
  const save = jest.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('unavailable'));
  await expect(importLegacy('a', local, save)).rejects.toThrow('unavailable');
  expect(pendingImports('a', local).map(r => r.id)).toEqual(['second']);
  expect(pendingImports('b', local)).toHaveLength(2);
  save.mockResolvedValue(undefined); await importLegacy('a', local, save);
  expect(pendingImports('a', local)).toEqual([]);
});

test.each([[401, 'session expired'], [403, 'Permission denied'], [503, 'Supabase account storage']])('HTTP %s has a distinct account error', async (status, message) => {
  signedIn(); global.fetch = jest.fn().mockResolvedValue(json({ error: { code: 'supabase_unavailable' } }, status as number));
  await expect(accountRequest('/api/preferences')).rejects.toThrow(message as string);
});

test('network failure is distinguished from Supabase failure', async () => {
  signedIn(); global.fetch = jest.fn().mockRejectedValue(new TypeError('network'));
  await expect(accountRequest('/api/preferences')).rejects.toThrow('MealMind backend is unavailable');
});

test('expired session clears visible account data and asks for sign-in', async () => {
  signedIn(); render(<Providers><Probe /></Providers>);
  await screen.findByText('a@example.com');
  act(() => { window.dispatchEvent(new Event('mealmind:auth-expired')); });
  await screen.findByText('Signed out');
  expect(screen.getByText(/Your session expired/)).toBeInTheDocument();
});

test('switching accounts hides old saved rows immediately', async () => {
  signedIn(); rows = [{ id: 'row-0', source_id: snapshot.id, recipe: snapshot }];
  render(<Providers><SavedRecipes onNavigate={jest.fn()} /></Providers>);
  await screen.findByRole('heading', { name: snapshot.name });
  rows = []; session = { user: { id: 'b', email: 'b@example.com' }, access_token: 'b-token' };
  act(() => { listener('SIGNED_IN', session); });
  expect(screen.queryByRole('heading', { name: snapshot.name })).not.toBeInTheDocument();
  await screen.findByText('Your next favorite starts here');
});


test('Create Recipe loads account preferences and explicitly saves updated defaults', async () => {
  signedIn(); preferences = { ...emptyPreferences, allergies: ['nuts'], excluded_ingredients: ['rice'], nutrition_targets: { protein_target: 35 } };
  render(<Providers><RecipeGenerator onNavigate={jest.fn()} /></Providers>);
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/preferences'), expect.anything()));
  await act(async () => {});
  fireEvent.click(screen.getAllByRole('button', { name: 'Tofu' })[0]);
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
  expect(screen.getByLabelText('Excluded ingredients (comma-separated)')).toHaveValue('rice');
  expect(screen.getByLabelText('Tree Nuts')).toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: 'Save as my preferences' }));
  await screen.findByText('Preferences saved to your account.');
  expect(preferences.nutrition_targets.protein_target).toBe(35);
  expect(preferences.allergies).toEqual(['nuts']);
});

test('token refresh updates future authenticated requests', async () => {
  signedIn(); render(<Providers><Probe /></Providers>);
  await screen.findByText('Data ready');
  session = { user, access_token: 'new-token' };
  act(() => { listener('TOKEN_REFRESHED', session); });
  await accountRequest('/api/preferences');
  expect(global.fetch).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer new-token' }) }));
});


test('sign-out clears a private recipe opened through account navigation', async () => {
  signedIn(); rows = [{ id: 'row-0', source_id: snapshot.id, recipe: snapshot }];
  window.scrollTo = jest.fn();
  window.history.replaceState(null, '', '/#saved');
  render(<Providers><AppContent /></Providers>);
  await screen.findByRole('heading', { name: snapshot.name });
  fireEvent.click(screen.getByRole('button', { name: 'Open full recipe' }));
  expect(screen.getByRole('heading', { name: snapshot.name })).toBeInTheDocument();
  act(() => { session = null; listener('SIGNED_OUT', null); });
  await waitFor(() => expect(screen.queryByRole('heading', { name: snapshot.name })).not.toBeInTheDocument());
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: /Saved/ }));
  expect(screen.queryByRole('heading', { name: snapshot.name })).not.toBeInTheDocument();
  window.history.replaceState(null, '', '/');
});


async function openRecovery() {
  window.scrollTo = jest.fn();
  render(<Providers><AppContent /></Providers>);
  await act(async () => {});
  act(() => { signedIn(); listener('PASSWORD_RECOVERY', session); });
  await screen.findByRole('heading', { name: 'Set new password' });
}
function enterPasswords(confirm = 'new-password-123') {
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'new-password-123' } });
  fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: confirm } });
  fireEvent.click(screen.getByRole('button', { name: 'Update password' }));
}
test('PASSWORD_RECOVERY overrides normal navigation and mismatch stays local', async () => {
  await openRecovery();
  enterPasswords('different-password');
  expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match');
  expect(auth.updateUser).not.toHaveBeenCalled();
});
test('matching passwords update Supabase, show loading, complete recovery and retain session', async () => {
  let finish: any;
  auth.updateUser.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  await openRecovery(); enterPasswords();
  expect(auth.updateUser).toHaveBeenCalledWith({ password: 'new-password-123' });
  expect(screen.getByRole('button', { name: /Updating password/ })).toBeDisabled();
  act(() => listener('USER_UPDATED', session));
  expect(screen.getByRole('heading', { name: 'Set new password' })).toBeInTheDocument();
  await act(async () => { finish({ error: null }); });
  expect(await screen.findByRole('status')).toHaveTextContent('Password updated successfully');
  expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
  expect(await screen.findByText('a@example.com')).toBeInTheDocument();
});
test.each(['response', 'network'])('password update %s failure is sanitized and remains recoverable', async kind => {
  if (kind === 'response') auth.updateUser.mockResolvedValue({ error: { message: 'private-provider-detail' } });
  else auth.updateUser.mockRejectedValue(new Error('private-provider-detail'));
  await openRecovery(); enterPasswords();
  expect(await screen.findByRole('alert')).toHaveTextContent('Password could not be updated');
  expect(screen.queryByText(/private-provider-detail/)).not.toBeInTheDocument();
  expect(screen.getByLabelText('New password')).toHaveValue('');
  expect(screen.getByLabelText('Confirm new password')).toHaveValue('');
});
test('recovery detected before React mounts is restored for the same session', async () => {
  signedIn(); (isRecoverySession as jest.Mock).mockReturnValueOnce(true);
  render(<Providers><AppContent /></Providers>);
  await screen.findByRole('heading', { name: 'Set new password' });
  act(() => { listener('SIGNED_OUT', null); });
  expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
});
test('normal restored session does not show password recovery', async () => {
  signedIn(); render(<Providers><AppContent /></Providers>);
  await act(async () => {});
  expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
});
