import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import { parseGenerationResponse, formatCalculatedNutrient, displayNutrition, toSavedRecipe } from './recipeApi';
import RecipeDetail from './components/RecipeDetail';
import RecipeResults from './components/RecipeResults';
import { readRecipes, saveRecipe } from './recipeStorage';
import captured from './partialNutritionFixture.json';

afterEach(() => { cleanup(); localStorage.clear(); });
const recipe = () => parseGenerationResponse(JSON.parse(JSON.stringify(captured))).recipe;

test('real six ingredient recipe displays useful partial values in Detail and Results', () => {
  const value = recipe();
  render(<RecipeDetail generatedRecipe={value} onNavigate={jest.fn()} />);
  expect(screen.getByText('267.66 kcal')).toBeInTheDocument();
  expect(screen.getByText('49.57 g')).toBeInTheDocument();
  expect(screen.getByText('4.41 g')).toBeInTheDocument();
  expect(screen.getAllByText(/Nutrition uses available USDA data/)).toHaveLength(1);
  expect(screen.getAllByText('Partial data')).toHaveLength(6);
  expect(screen.queryByText(/from matched ingredients/)).not.toBeInTheDocument();
  cleanup(); render(<RecipeResults generatedRecipe={value} onNavigate={jest.fn()} />);
  expect(screen.getByText('267.66 kcal')).toBeInTheDocument();
  expect(screen.getAllByText(/Nutrition uses available USDA data/)).toHaveLength(1);
  expect(screen.getAllByText('Partial data')).toHaveLength(2);
});

test('full, partial zero, missing and sugar stay distinct', () => {
  const value = recipe(); const n = value.intelligence!.calculated_nutrition;
  n.per_serving.calories = 300;
  expect(formatCalculatedNutrient(value, 'calories')).toBe('300 kcal');
  n.per_serving.calories = null; n.known_per_serving.calories = 0;
  expect(formatCalculatedNutrient(value, 'calories')).toBe('Unknown');
  n.known_per_serving.calories = null;
  expect(formatCalculatedNutrient(value, 'calories')).toBe('Unknown');
  expect(formatCalculatedNutrient(value, 'sugar')).toBe('Unknown');
  n.known_per_serving.sugar = 2;
  expect(formatCalculatedNutrient(value, 'sugar')).toBe('2 g');
});

test('presentation does not replace authoritative totals and persists known contributions', () => {
  const value = recipe(); formatCalculatedNutrient(value, 'calories');
  expect(displayNutrition(value).calories).toBeNull();
  saveRecipe(toSavedRecipe(value));
  const saved = readRecipes()[0]; expect(saved.nutrition.calories).toBeNull();
  expect(formatCalculatedNutrient(saved.structuredRecipe!, 'calories')).toContain('267.66 kcal');
  expect(saved.structuredRecipe!.intelligence!.constraint_results.find(r => r.constraint === 'maximum_calories')!.passed).toBeNull();
});


test.each(['calories', 'protein', 'carbohydrates', 'fat', 'fiber', 'sugar', 'sodium'] as const)(
  '%s partial zero is Unknown, complete zero remains zero', nutrient => {
    const value = recipe(); const n = value.intelligence!.calculated_nutrition;
    n.per_serving[nutrient] = null; n.known_per_serving[nutrient] = 0;
    expect(formatCalculatedNutrient(value, nutrient)).toBe('Unknown');
    n.per_serving[nutrient] = 0;
    expect(formatCalculatedNutrient(value, nutrient)).toBe(`0 ${nutrient === 'calories' ? 'kcal' : nutrient === 'sodium' ? 'mg' : 'g'}`);
  });

test('tiny partial positive contribution never rounds into a zero claim', () => {
  const value = recipe(); const n = value.intelligence!.calculated_nutrition;
  n.per_serving.sugar = null; n.known_per_serving.sugar = .001;
  expect(formatCalculatedNutrient(value, 'sugar')).toBe('<0.01 g');
});
