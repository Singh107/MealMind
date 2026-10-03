import { testAccount } from './accountTestFixtures';
import { mockGenerationFetch } from './recipeTestFixtures';
import React from 'react';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import App from './App';
import RecipeGenerator from './components/RecipeGenerator';
import SavedRecipes from './components/SavedRecipes';


beforeEach(() => {
  mockGenerationFetch();
  localStorage.clear();
  window.history.replaceState(null, '', '/');
  window.scrollTo = jest.fn();
});

test('new kitchen home routes to studio with floating navigation', () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: 'Welcome to your kitchen' })).toBeInTheDocument();
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('button', { name: 'Studio' }));
  expect(screen.getByRole('searchbox', { name: 'Search for ingredients' })).toBeInTheDocument();
});

test('profile action opens real sign in instead of a fabricated account', () => {
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(screen.getByRole('heading', { name: 'Sign In' })).toBeInTheDocument();
  expect(screen.queryByText(/Chef Maya/)).not.toBeInTheDocument();
});

test('search selects ingredients and saved recipe survives remount and removal', async () => {
  jest.useFakeTimers();
  const navigate = jest.fn();
  const account = testAccount();
  const generator = render(<account.Provider><RecipeGenerator onNavigate={navigate} /></account.Provider>);
  expect(screen.getByRole('button', { name: 'Select Ingredients' })).toBeDisabled();
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search for ingredients' }), { target: { value: 'Lentil' } });
  fireEvent.click(within(screen.getByLabelText('Ingredient search results')).getByRole('button', { name: 'Lentils' }));
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Preferences' }));
  fireEvent.click(screen.getByRole('button', { name: /Create Recipe/ }));
  await act(async () => { jest.advanceTimersByTime(2100); });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save Recipe' })); });
  expect(navigate).toHaveBeenCalledWith('saved');
  expect(account.store.rows[0].recipe.ingredients).toEqual(['200 g Lentils', '300 g Tomatoes']);
  generator.unmount();
  render(<account.Provider><SavedRecipes onNavigate={navigate} /></account.Provider>);
  expect(screen.getByRole('heading', { name: 'Lentil and Tomato Stew' })).toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'unmatched' } });
  expect(screen.getByText('No matching recipes')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  fireEvent.click(screen.getByRole('button', { name: 'View details' }));
  expect(screen.getByRole('heading', { name: 'Instructions' })).toBeInTheDocument();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Remove Lentil and Tomato Stew' })); });
  expect(account.store.rows).toEqual([]);
  jest.useRealTimers();
});

test('corrupt saved data shows a recovery message', () => {
  localStorage.setItem('mealmind.savedRecipes.v1', '{broken');
  render(<SavedRecipes onNavigate={jest.fn()} />);
  expect(screen.getByRole('alert')).toHaveTextContent('could not be loaded');
});
