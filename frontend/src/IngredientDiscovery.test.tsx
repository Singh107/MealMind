import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { searchIngredients } from './ingredientCatalog';
import IngredientAutocomplete from './components/IngredientAutocomplete';
import RecipeGenerator from './components/RecipeGenerator';

test('offline alias and prefix search use deterministic canonical results', () => {
  expect(searchIngredients('rajma')[0].name).toBe('Kidney beans');
  expect(searchIngredients('kidney')[0].name).toBe('Kidney beans');
  expect(searchIngredients('garbanzo')[0].name).toBe('Chickpeas');
  expect(searchIngredients('chick').map(x=>x.name).slice(0,2)).toEqual(['Chicken','Chicken Breast']);
  expect(searchIngredients('red--kidney beans')).toEqual(searchIngredients('RED KIDNEY BEANS'));
  expect(searchIngredients('unlisted regional ingredient')).toEqual([]);
});

test('Studio alias selection adds canonical display name without changing the flow', () => {
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  fireEvent.change(screen.getByPlaceholderText(/Search for ingredients/i), {target:{value:'rajma'}});
  fireEvent.click(screen.getByRole('button',{name:'Kidney beans'}));
  expect(screen.getByRole('button',{name:'Remove Kidney beans'})).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Continue to Preferences'})).toBeEnabled();
});

test('Studio unknown custom name remains selectable', () => {
  render(<RecipeGenerator onNavigate={jest.fn()} />);
  fireEvent.change(screen.getByPlaceholderText(/Search for ingredients/i), {target:{value:'Regional herb mix'}});
  fireEvent.click(screen.getByRole('button',{name:'Add ingredient'}));
  expect(screen.getByRole('button',{name:'Remove Regional herb mix'})).toBeInTheDocument();
});

function Harness() {
  const [value,setValue]=useState('');
  return <IngredientAutocomplete value={value} onChange={setValue} disabled={false} />;
}

test('typeahead is collapsed initially, filters and restores focus after click', () => {
  render(<Harness />);
  const input=screen.getByRole('combobox');
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  fireEvent.change(input,{target:{value:'chick'}});
  expect(screen.getAllByRole('option').length).toBeLessThanOrEqual(6);
  fireEvent.click(screen.getByRole('option',{name:'Chicken Breast'}));
  expect(input).toHaveValue('Chicken Breast');
  expect(input).toHaveFocus();
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
});

test('arrows and Enter select, Escape closes without replacing typed text', () => {
  render(<Harness />); const input=screen.getByRole('combobox');
  fireEvent.change(input,{target:{value:'rajma'}});
  fireEvent.keyDown(input,{key:'ArrowDown'});
  fireEvent.keyDown(input,{key:'Enter'});
  expect(input).toHaveValue('Kidney beans');
  fireEvent.change(input,{target:{value:'chick'}});
  fireEvent.keyDown(input,{key:'Escape'});
  expect(input).toHaveValue('chick');
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
});
