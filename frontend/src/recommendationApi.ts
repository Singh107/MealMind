import { accountRequest } from './accountApi';
import { GeneratedRecipe, isGeneratedRecipe } from './recipeApi';

export interface Recommendation {
  saved_recipe_id: string; recipe: GeneratedRecipe; eligibility: 'eligible' | 'uncertain'; rank: number; score: number;
  reasons: { code: string; text: string }[];
}
export interface Recommendations {
  state: 'empty_pantry' | 'no_candidates' | 'all_ineligible' | 'only_uncertain' | 'ready';
  entries: Recommendation[]; total: number; candidate_count: number; skipped_count: number; ineligible_count: number;
}
export async function getPantryRecommendations(owner: string): Promise<Recommendations> {
  const data = await accountRequest<Recommendations>('/api/recommendations/pantry?limit=20', 'GET', undefined, owner);
  if (!data || !Array.isArray(data.entries) || !data.entries.every(x => isGeneratedRecipe(x.recipe) &&
    ['eligible', 'uncertain'].includes(x.eligibility) && Array.isArray(x.reasons) && x.reasons.every(r => typeof r.text === 'string'))) {
    throw new Error('Pantry matches could not be read. Please try again.');
  }
  return data;
}
