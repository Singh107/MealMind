import { RecipeGenerationResponse } from './recipeApi';

// Test fixture only: never imported by application components.
export const generationFixture: RecipeGenerationResponse = {
  recipe: {
    id: '11111111-1111-4111-8111-111111111111', recipe_version_id: '22222222-2222-4222-8222-222222222222',
    title: 'Lentil and Tomato Stew', description: 'A simple lentil stew with tomatoes.',
    ingredients: [{ name: 'Lentils', quantity: 200, unit: 'g' }, { name: 'Tomatoes', quantity: 300, unit: 'g' }],
    instructions: ['Rinse lentils and dice tomatoes.', 'Simmer until the lentils are tender.'],
    prep_time: 10, cook_time: 25, total_time: 35, servings: 4,
    cuisine: 'mediterranean', difficulty: 'beginner', dietary_tags: ['vegan'], potential_allergens: [],
    nutrition: { calories: 210, protein: 14, carbohydrates: 35, fat: 1, fiber: 8, sodium: null },
    validation_status: 'unverified', nutrition_source: 'ai_estimate', nutrition_basis: 'per_serving',
  },
  warnings: ['Nutrition and dietary suitability are unverified.'],
  metadata: { provider: 'test-provider', model: 'fixture-v1', prompt_version: 'recipe-v1', schema_version: '1.0' },
  trace_id: 'test-trace',
};

export function mockGenerationFetch(payload: unknown = generationFixture, status = 200) {
  const mock = jest.fn().mockImplementation((url: string) => Promise.resolve(url.endsWith('/health')
    ? { ok: true, status: 200, json: async () => ({ status: 'ok' }) }
    : { ok: status >= 200 && status < 300, status, json: async () => payload }));
  global.fetch = mock;
  return mock;
}
