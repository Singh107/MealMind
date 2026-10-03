import { ingredientCatalog, searchIngredients, cleanSearch } from '../ingredientCatalog';
import { useAuth } from '../AuthContext';
import { useUserData } from '../UserDataContext';
import NutritionValue, { PartialNutritionNote } from './NutritionValue';
import React, { useEffect, useRef, useState } from 'react';
import { SavedRecipe } from '../recipeStorage';
import { formatNutrient, generateRecipe, GeneratedRecipe, nutritionLabel, toSavedRecipe } from '../recipeApi';
import RecipeIntelligence from './RecipeIntelligence';

interface Ingredient {
  id: string;
  name: string;
  category: string;
}

const selectionKey = (name: string) => {
  const query = cleanSearch(name);
  const entry = ingredientCatalog.find(item => [item.name, item.canonical, ...item.aliases].some(alias => cleanSearch(alias) === query));
  return entry?.canonical || name.trim().toLowerCase().replace(/\s+/g, ' ');
};

type Recipe = Omit<SavedRecipe, 'savedAt'>;

interface Preferences {
  calories: number | '';
  protein: number | '';
  carbs: number | '';
  fat: number | '';
  cuisine: string;
  spiceLevel: string;
  cookTime: string;
  difficulty: string;
  servings: number | '';
  dietaryPreferences: string[];
  allergies: string[];
  mealType: string;
  excludedIngredients: string;
}

interface RecipeGeneratorProps {
  initialIngredients?: string[];
  onNavigate: (section: string) => void;
  onGenerated?: (recipe: GeneratedRecipe) => void;
  onOpenRecipe?: (recipe: GeneratedRecipe) => void;
}

const RecipeGenerator: React.FC<RecipeGeneratorProps> = ({ onNavigate, onGenerated, onOpenRecipe, initialIngredients = [] }) => {
  const cloud = useUserData();
  const auth = useAuth();
  const [preferenceStatus, setPreferenceStatus] = useState('');
  const [step, setStep] = useState(1); // 1: ingredients, 2: preferences, 3: results
  const [selectedIngredients, setSelectedIngredients] = useState<string[]>(() => Array.from(new Map(initialIngredients.map(name => name.trim()).filter(Boolean).map(name => [selectionKey(name), name])).values()).slice(0, 50));
  const [searchQuery, setSearchQuery] = useState('');
  const [openCategory, setOpenCategory] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences>({
    calories: '',
    protein: '',
    carbs: '',
    fat: '',
    cuisine: '',
    spiceLevel: '',
    cookTime: '',
    difficulty: '',
    servings: '',
    dietaryPreferences: [],
    allergies: [],
    mealType: '',
    excludedIngredients: ''
  });
  useEffect(() => {
    const p = cloud.preferences;
    setPreferences(previous => ({ ...previous,
      calories: p.nutrition_targets.calorie_target ?? '', protein: p.nutrition_targets.protein_target ?? '',
      carbs: p.nutrition_targets.carbs_target ?? '', fat: p.nutrition_targets.fat_target ?? '',
      cuisine: p.preferred_cuisines[0] || '', dietaryPreferences: p.dietary_preferences,
      allergies: p.allergies, excludedIngredients: p.excluded_ingredients.join(', '),
      spiceLevel: p.cooking_preferences.spice_level || '', cookTime: p.cooking_preferences.max_cooking_time?.toString() || '',
      difficulty: p.cooking_preferences.difficulty || '', servings: p.cooking_preferences.servings ?? '', mealType: p.cooking_preferences.meal_type || '',
    }));
  }, [cloud.preferences]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedRecipe, setGeneratedRecipe] = useState<Recipe | null>(null);
  const [saveError, setSaveError] = useState('');
  const [generationError, setGenerationError] = useState('');
  const generationController = useRef<AbortController | null>(null);
  useEffect(() => () => {
    generationController.current?.abort();
    generationController.current = null;
  }, [auth.user?.id]);
  const cancelGeneration = () => {
    generationController.current?.abort();
    generationController.current = null;
    setIsGenerating(false);
  };

  const allIngredients = ingredientCatalog;
  const filteredIngredients = searchIngredients(searchQuery, 10);
  const isSelected = (name: string) => selectedIngredients.some(selected => selectionKey(selected) === selectionKey(name));

  const handleIngredientSelect = (ingredient: Ingredient) => {
    setSelectedIngredients(current => current.some(name => selectionKey(name) === selectionKey(ingredient.name))
      ? current.filter(name => selectionKey(name) !== selectionKey(ingredient.name))
      : [...current, ingredient.name].slice(0, 50));
  };

  const handleIngredientRemove = (ingredientName: string) => {
    setSelectedIngredients(selectedIngredients.filter(ing => ing !== ingredientName));
  };

  const handlePreferenceChange = (field: keyof Preferences, value: any) => {
    setPreferences(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleGenerate = async () => {
    if (generationController.current || auth.loading || cloud.loading) return;
    if (!selectedIngredients.length) {
      setGenerationError('Please select at least one ingredient.');
      return;
    }
    const controller = new AbortController();
    generationController.current = controller;
    setIsGenerating(true);
    setGenerationError('');
    setSaveError('');
    try {
      const response = await generateRecipe({
        selected_ingredients: selectedIngredients,
        calorie_target: preferences.calories === '' ? null : preferences.calories,
        protein_target: preferences.protein === '' ? null : preferences.protein,
        carbs_target: preferences.carbs === '' ? null : preferences.carbs,
        fat_target: preferences.fat === '' ? null : preferences.fat,
        cuisine: preferences.cuisine || null, spice_level: preferences.spiceLevel || null,
        max_cooking_time: preferences.cookTime ? Number(preferences.cookTime) : null,
        difficulty: preferences.difficulty || null, servings: preferences.servings === '' ? 4 : preferences.servings,
        dietary_preferences: preferences.dietaryPreferences, allergies: preferences.allergies,
        excluded_ingredients: preferences.excludedIngredients.split(',').map(value => value.trim()).filter(Boolean),
        meal_type: preferences.mealType || null,
      }, controller.signal, auth.accessToken);
      if (controller.signal.aborted || generationController.current !== controller) return;
      setGeneratedRecipe(toSavedRecipe(response.recipe));
      onGenerated?.(response.recipe);
      setStep(3);
    } catch (error) {
      if (!controller.signal.aborted && generationController.current === controller) {
        setGenerationError(error instanceof Error ? error.message : 'Recipe generation failed. Please try again.');
      }
    } finally {
      if (generationController.current === controller) {
        generationController.current = null;
        setIsGenerating(false);
      }
    }
  };

  const handleReset = () => {
    cancelGeneration();
    setSaveError('');
    setGenerationError('');
    setStep(1);
    setSelectedIngredients([]);
    setSearchQuery('');
    setPreferences({
      calories: '',
      protein: '',
      carbs: '',
      fat: '',
      cuisine: '',
      spiceLevel: '',
      cookTime: '',
      difficulty: '',
      servings: '',
      dietaryPreferences: [],
      allergies: [],
      mealType: '',
      excludedIngredients: ''
    });
    setGeneratedRecipe(null);
  };

  if (step === 1) {
    // Step 1: Ingredient Selection
    return (
      <section id="generator" className="py-6 bg-surface-container">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          {/* Header */}
          <div className="mb-6 text-left">
            <h2 className="text-3xl font-bold text-on-surface">Recipe Studio</h2>
            <p className="mt-3 text-lg text-on-surface-variant">
              Start by selecting the ingredients you have available
            </p>
          </div>

          {/* Progress Indicator */}
          <div className="mb-6 flex w-full items-center justify-between">
            <div className="flex-1 h-0.5 bg-surface-container-highest"></div>
            <div className="flex items-center space-x-3">
              <div className="w-2 h-2 rounded-full bg-primary-container"></div>
              <span className="text-xs font-medium text-on-surface-variant">Step 1 of 3</span>
            </div>
            <div className="flex-1 h-0.5 bg-surface-container-highest"></div>
          </div>

          {/* Main Content */}
          <div className="grid gap-8">
            {/* Left Side - Ingredient Selection */}
            <div className="space-y-6 rounded-2xl bg-surface-container p-4 sm:p-5">
              <div>
                <label htmlFor="ingredient-search" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Search for ingredients
                </label>
                <div className="relative">
                  <input
                    id="ingredient-search"
                    type="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search for ingredients (e.g., chicken, broccoli, rice)..."
                    className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary pl-10"
                  />
                  <div className="absolute left-3 top-1/2 -translate-y-1/2 flex h-4 w-4 items-center justify-center text-outline">
                    <svg className="h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17.822 17.822l-1.414-1.414M5.5 5.5a5 5 0 1110 0H5.5z" />
                    </svg>
                  </div>
                </div>
                {searchQuery.trim() && filteredIngredients.length > 0 && (
                  <div aria-label="Ingredient search results" className="mt-2 grid gap-2 rounded-2xl border border-border p-3 sm:grid-cols-2">
                    {filteredIngredients.map(ingredient => <button type="button" key={ingredient.id} aria-pressed={isSelected(ingredient.name)} onClick={() => handleIngredientSelect(ingredient)} className={`rounded-2xl px-3 py-3 text-left text-sm ${isSelected(ingredient.name) ? 'bg-primary-container text-on-primary-container ring-1 ring-primary' : 'hover:bg-surface-container-high'}`}>{ingredient.name}</button>)}
                  </div>
                )}
                {searchQuery.length > 0 && filteredIngredients.length === 0 && (
                  <p className="mt-2 text-sm text-outline italic">
                    No ingredients found. Try a different search.
                    {searchQuery.trim() && <button type="button" className="mm-button mt-3 block" onClick={() => handleIngredientSelect({ id: 'custom', name: searchQuery.trim(), category: 'Custom' })}>Add ingredient</button>}
                  </p>
                )}
              </div>

              {/* Ingredient Categories */}
              <div className="space-y-4">
                {/* Popular Ingredients */}
                <div>
                  <h3 className="text-lg font-semibold text-on-surface mb-3">Popular Ingredients</h3>
                  <div className="flex flex-wrap gap-2">
                    {['Chicken Breast', 'Ground Beef', 'Salmon', 'Tofu', 'Eggs', 'Broccoli', 'Spinach', 'Bell Peppers', 'Brown Rice', 'Quinoa'].map(ingredient => (
                      <button
                        key={ingredient}
                        aria-pressed={isSelected(ingredient)}
                        onClick={() => {
                          const ing = allIngredients.find(i => i.name === ingredient);
                          if (ing) handleIngredientSelect(ing);
                        }}
                        className={`px-3 py-1 rounded-full text-sm font-medium
                                ${isSelected(ingredient)
                                  ? 'bg-primary-container text-on-surface'
                                  : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-high'}`}
                        >
                          {ingredient}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <h3 className="text-lg font-semibold">Browse ingredients</h3>
                  <div className="flex flex-wrap gap-2" aria-label="Ingredient categories">
                    {Array.from(new Set(allIngredients.map(item => item.category))).map(category => (
                      <button key={category} type="button" aria-expanded={openCategory === category}
                        aria-controls="ingredient-category-options"
                        onClick={() => setOpenCategory(openCategory === category ? null : category)}
                        className={`min-h-[44px] rounded-full px-3 py-2 text-sm ${openCategory === category ? 'bg-secondary/15 text-secondary border border-secondary/40' : 'bg-surface-container-low text-on-surface-variant border border-border'}`}>
                        {category}<span aria-hidden="true">{openCategory === category ? ' \u2212' : ' +'}</span>
                      </button>
                    ))}
                  </div>
                  <div id="ingredient-category-options" hidden={!openCategory}>
                    {openCategory && <div role="group" aria-label={`${openCategory} ingredients`} className="rounded-2xl bg-surface-container-low p-3">
                      <p className="text-sm text-secondary mb-2">{openCategory}</p>
                      <div className="flex flex-wrap gap-2">{allIngredients.filter(item => item.category === openCategory).map(ingredient => (
                        <button key={ingredient.id} type="button" aria-pressed={isSelected(ingredient.name)}
                          onClick={() => handleIngredientSelect(ingredient)}
                          className={`min-h-[44px] rounded-full px-3 py-2 text-sm ${isSelected(ingredient.name) ? 'bg-primary-container text-on-primary-container' : 'bg-surface-container-high text-on-surface'}`}>
                          {ingredient.name}
                        </button>
                      ))}</div>
                    </div>}
                  </div>
                </div>
              </div>
            </div>

            {/* Right Side - Selected Ingredients */}
            <div className="space-y-4 mm-panel self-start">
              <div>
                <h3 className="text-lg font-semibold text-on-surface mb-3">
                  Selected Ingredients ({selectedIngredients.length})
                </h3>
                {selectedIngredients.length === 0 ? (
                  <p className="rounded-xl bg-surface-container-low p-6 text-center text-on-surface-variant">
                    No ingredients selected yet. Search or browse to add what you have.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {selectedIngredients.map(ingredient => (
                      <div key={ingredient} className="flex min-w-0 max-w-full items-center bg-surface-container-low px-3 py-1 rounded-full text-sm">
                        <span className="mr-2 min-w-0">{ingredient}</span>
                        <button
                          aria-label={`Remove ${ingredient}`}
                          onClick={() => handleIngredientRemove(ingredient)}
                          className="shrink-0 text-outline hover:text-on-surface-variant"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
              <label htmlFor="excluded-ingredients" className="block text-sm font-medium text-on-surface-variant mb-2">Excluded ingredients (comma-separated)</label>
              <input id="excluded-ingredients" value={preferences.excludedIngredients} maxLength={2000}
                onChange={event => handlePreferenceChange('excludedIngredients', event.target.value)}
                placeholder="e.g., mushrooms, olives" className="w-full px-4 py-3 border border-border rounded-full" />
            </div>
            {/* Navigation Buttons */}
              <div className="mt-8 pt-6 border-t border-border">
                <button
                  onClick={handleReset}
                  className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium text-on-surface-variant bg-surface-container hover:bg-surface-container-low border border-border rounded-full"
                >
                  <span className="mr-2">↺</span>
                  Clear All
                </button>
                <button
                  onClick={() => setStep(2)}
                  disabled={selectedIngredients.length === 0}
                  className="w-full mt-3 flex items-center justify-center px-4 py-3 text-sm font-semibold mm-action rounded-md shadow-soft"
                >
                  {selectedIngredients.length === 0 ? 'Select Ingredients' : 'Continue to Preferences'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  }

  if (step === 2) {
    // Step 2: Preferences
    return (
      <section id="generator" className="py-6 bg-surface-container">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          {/* Header */}
          <div className="mb-6 text-left">
            <h2 className="text-3xl font-bold text-on-surface">Recipe Studio</h2>
            <p className="mt-3 text-lg text-on-surface-variant">
              Customize your recipe based on your preferences and dietary needs
            </p>
          </div>

          {/* Progress Indicator */}
          <div className="mb-6 flex w-full items-center justify-between">
            <div className="flex-1 h-0.5 bg-surface-container-highest"></div>
            <div className="flex items-center space-x-3">
              <div className="w-2 h-2 rounded-full bg-surface-container-low"></div>
              <div className="w-2 h-2 rounded-full bg-primary-container"></div>
              <span className="text-xs font-medium text-on-surface-variant">Step 2 of 3</span>
            </div>
            <div className="flex-1 h-0.5 bg-surface-container-highest"></div>
          </div>

          {/* Preferences Form */}
          <form onSubmit={(e) => { e.preventDefault(); if (!isGenerating) void handleGenerate(); }} className="space-y-8">
            <p className="text-sm text-on-surface-variant">Per-serving targets: calories, carbs and fat are maxima; protein is a minimum. Checks use calculated food data when available. Blank servings defaults to 4; additional ingredients may be needed.</p>
            {generationError && <p role="alert" className="rounded-2xl bg-error-container/20 p-4 text-error">{generationError}</p>}
            {isGenerating && <p role="status" className="text-sm text-primary">Generating your recipe...</p>}
            {auth.signedIn && <div className="mb-4">
              {cloud.loading && <p role="status">Loading saved preferences...</p>}
              {cloud.error && <p role="alert">{cloud.error}</p>}
              {preferenceStatus && <p role="status">{preferenceStatus}</p>}
              <button disabled={cloud.loading || !!cloud.error || isGenerating} onClick={async () => {
                try {
                  await cloud.savePreferences({ dietary_preferences: preferences.dietaryPreferences, allergies: preferences.allergies,
                    excluded_ingredients: preferences.excludedIngredients.split(',').map(x => x.trim()).filter(Boolean),
                    preferred_cuisines: preferences.cuisine ? [preferences.cuisine, ...cloud.preferences.preferred_cuisines.filter(x => x !== preferences.cuisine)] : [],
                    nutrition_targets: { calorie_target: preferences.calories === '' ? null : preferences.calories,
                      protein_target: preferences.protein === '' ? null : preferences.protein, carbs_target: preferences.carbs === '' ? null : preferences.carbs, fat_target: preferences.fat === '' ? null : preferences.fat },
                    cooking_preferences: { spice_level: preferences.spiceLevel || null, max_cooking_time: preferences.cookTime ? Number(preferences.cookTime) : null,
                      difficulty: preferences.difficulty || null, servings: preferences.servings === '' ? 4 : preferences.servings, meal_type: preferences.mealType || null } });
                  setPreferenceStatus('Preferences saved to your account.');
                } catch (error) { setPreferenceStatus((error as Error).message); }
              }} className="rounded-2xl border px-4 py-2 text-primary">Save as my preferences</button>
            </div>}
            <fieldset disabled={isGenerating || cloud.loading} className="contents">
            {/* Basic Nutrition */}
            <div className="mm-panel grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="pref-calories" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Target Calories (per serving)
                </label>
                <input id="pref-calories"
                  type="number"
                  min="0"
                  max="2000"
                  value={preferences.calories === '' ? '' : preferences.calories}
                  onChange={(e) => handlePreferenceChange('calories', e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                  placeholder="e.g., 500"
                />
              </div>
              <div>
                <label htmlFor="pref-protein" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Protein (g)
                </label>
                <input id="pref-protein"
                  type="number"
                  min="0"
                  max="200"
                  value={preferences.protein === '' ? '' : preferences.protein}
                  onChange={(e) => handlePreferenceChange('protein', e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                  placeholder="e.g., 30"
                />
              </div>
              <div>
                <label htmlFor="pref-carbs" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Carbs (g)
                </label>
                <input id="pref-carbs"
                  type="number"
                  min="0"
                  max="300"
                  value={preferences.carbs === '' ? '' : preferences.carbs}
                  onChange={(e) => handlePreferenceChange('carbs', e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                  placeholder="e.g., 50"
                />
              </div>
              <div>
                <label htmlFor="pref-fat" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Fat (g)
                </label>
                <input id="pref-fat"
                  type="number"
                  min="0"
                  max="100"
                  value={preferences.fat === '' ? '' : preferences.fat}
                  onChange={(e) => handlePreferenceChange('fat', e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                  placeholder="e.g., 20"
                />
              </div>
            </div>

            {/* Cuisine & Cooking Preferences */}
            <div className="mm-panel grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="pref-cuisine" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Cuisine Type
                </label>
                <select id="pref-cuisine"
                  value={preferences.cuisine}
                  onChange={(e) => handlePreferenceChange('cuisine', e.target.value)}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                >
                  <option value="">Any cuisine</option>
                  <option value="italian">Italian</option>
                  <option value="mexican">Mexican</option>
                  <option value="asian">Asian</option>
                  <option value="indian">Indian</option>
                  <option value="mediterranean">Mediterranean</option>
                  <option value="american">American</option>
                  <option value="thai">Thai</option>
                  <option value="chinese">Chinese</option>
                </select>
              </div>
              <div>
                <label htmlFor="pref-spiceLevel" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Spice Level
                </label>
                <select id="pref-spiceLevel"
                  value={preferences.spiceLevel}
                  onChange={(e) => handlePreferenceChange('spiceLevel', e.target.value)}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                >
                  <option value="">No preference</option>
                  <option value="mild">Mild</option>
                  <option value="medium">Medium</option>
                  <option value="spicy">Spicy</option>
                  <option value="very-spicy">Very Spicy</option>
                </select>
              </div>
              <div>
                <label htmlFor="pref-cookTime" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Max Cook Time
                </label>
                <select id="pref-cookTime"
                  value={preferences.cookTime}
                  onChange={(e) => handlePreferenceChange('cookTime', e.target.value)}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                >
                  <option value="">No limit</option>
                  <option value="15">15 minutes</option>
                  <option value="30">30 minutes</option>
                  <option value="60">1 hour</option>
                  <option value="120">2 hours</option>
                </select>
              </div>
              <div>
                <label htmlFor="pref-difficulty" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Difficulty
                </label>
                <select id="pref-difficulty"
                  value={preferences.difficulty}
                  onChange={(e) => handlePreferenceChange('difficulty', e.target.value)}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                >
                  <option value="">Any difficulty</option>
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </select>
              </div>
            </div>

            {/* Servings & Dietary */}
            <div className="mm-panel grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="pref-servings" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Servings
                </label>
                <input id="pref-servings"
                  type="number"
                  min="1"
                  max="12"
                  value={preferences.servings === '' ? '' : preferences.servings}
                  onChange={(e) => handlePreferenceChange('servings', e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                  placeholder="e.g., 4"
                />
              </div>
              <div>
                <label htmlFor="pref-mealType" className="block text-sm font-medium text-on-surface-variant mb-2">
                  Meal Type
                </label>
                <select id="pref-mealType"
                  value={preferences.mealType || ''}
                  onChange={(e) => handlePreferenceChange('mealType', e.target.value)}
                  className="w-full px-4 py-3 border border-border rounded-full focus:ring-2 focus:ring-primary focus:border-primary"
                >
                  <option value="">Any meal type</option>
                  <option value="breakfast">Breakfast</option>
                  <option value="lunch">Lunch</option>
                  <option value="dinner">Dinner</option>
                  <option value="snack">Snack</option>
                  <option value="dessert">Dessert</option>
                </select>
              </div>
            </div>

            {/* Dietary Preferences & Allergies */}
            <div className="space-y-6 rounded-2xl bg-surface-container p-4 sm:p-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <h3 className="text-lg font-semibold text-on-surface mb-4">Dietary Preferences</h3>
                  <div className="space-y-2">
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.dietaryPreferences.includes('vegetarian')}
                        onChange={(e) => {
                          const newPrefs = e.target.checked
                            ? [...preferences.dietaryPreferences, 'vegetarian']
                            : preferences.dietaryPreferences.filter(p => p !== 'vegetarian');
                          handlePreferenceChange('dietaryPreferences', newPrefs);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Vegetarian</span>
                    </label>
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.dietaryPreferences.includes('vegan')}
                        onChange={(e) => {
                          const newPrefs = e.target.checked
                            ? [...preferences.dietaryPreferences, 'vegan']
                            : preferences.dietaryPreferences.filter(p => p !== 'vegan');
                          handlePreferenceChange('dietaryPreferences', newPrefs);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Vegan</span>
                    </label>
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.dietaryPreferences.includes('gluten-free')}
                        onChange={(e) => {
                          const newPrefs = e.target.checked
                            ? [...preferences.dietaryPreferences, 'gluten-free']
                            : preferences.dietaryPreferences.filter(p => p !== 'gluten-free');
                          handlePreferenceChange('dietaryPreferences', newPrefs);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Gluten-Free</span>
                    </label>
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.dietaryPreferences.includes('dairy-free')}
                        onChange={(e) => {
                          const newPrefs = e.target.checked
                            ? [...preferences.dietaryPreferences, 'dairy-free']
                            : preferences.dietaryPreferences.filter(p => p !== 'dairy-free');
                          handlePreferenceChange('dietaryPreferences', newPrefs);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Dairy-Free</span>
                    </label>
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.dietaryPreferences.includes('nut-free')}
                        onChange={(e) => {
                          const newPrefs = e.target.checked
                            ? [...preferences.dietaryPreferences, 'nut-free']
                            : preferences.dietaryPreferences.filter(p => p !== 'nut-free');
                          handlePreferenceChange('dietaryPreferences', newPrefs);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Nut-Free</span>
                    </label>
                  </div>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-on-surface mb-4">Allergies</h3>
                  <div className="space-y-2">
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.allergies.includes('nuts')}
                        onChange={(e) => {
                          const newAllergies = e.target.checked
                            ? [...preferences.allergies, 'nuts']
                            : preferences.allergies.filter(a => a !== 'nuts');
                          handlePreferenceChange('allergies', newAllergies);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Tree Nuts</span>
                    </label>
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.allergies.includes('peanuts')}
                        onChange={(e) => {
                          const newAllergies = e.target.checked
                            ? [...preferences.allergies, 'peanuts']
                            : preferences.allergies.filter(a => a !== 'peanuts');
                          handlePreferenceChange('allergies', newAllergies);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Peanuts</span>
                    </label>
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.allergies.includes('shellfish')}
                        onChange={(e) => {
                          const newAllergies = e.target.checked
                            ? [...preferences.allergies, 'shellfish']
                            : preferences.allergies.filter(a => a !== 'shellfish');
                          handlePreferenceChange('allergies', newAllergies);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Shellfish</span>
                    </label>
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.allergies.includes('dairy')}
                        onChange={(e) => {
                          const newAllergies = e.target.checked
                            ? [...preferences.allergies, 'dairy']
                            : preferences.allergies.filter(a => a !== 'dairy');
                          handlePreferenceChange('allergies', newAllergies);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Dairy</span>
                    </label>
                    <label className="mm-check-target flex items-center">
                      <input
                        type="checkbox"
                        checked={preferences.allergies.includes('eggs')}
                        onChange={(e) => {
                          const newAllergies = e.target.checked
                            ? [...preferences.allergies, 'eggs']
                            : preferences.allergies.filter(a => a !== 'eggs');
                          handlePreferenceChange('allergies', newAllergies);
                        }}
                        className="h-4 w-4 text-primary"
                      />
                      <span className="ml-2 text-on-surface-variant">Eggs</span>
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <label htmlFor="excluded-ingredients" className="block text-sm font-medium text-on-surface-variant mb-2">Excluded ingredients (comma-separated)</label>
              <input id="excluded-ingredients" value={preferences.excludedIngredients} maxLength={2000}
                onChange={event => handlePreferenceChange('excludedIngredients', event.target.value)}
                placeholder="e.g., mushrooms, olives" className="w-full px-4 py-3 border border-border rounded-full" />
            </div>
            </fieldset>
            {/* Navigation Buttons */}
            <div className="mt-10 pt-8 border-t border-border">
              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={() => { cancelGeneration(); setStep(1); }}
                  className="flex items-center justify-center px-4 py-3 text-sm font-medium text-on-surface-variant bg-surface-container hover:bg-surface-container-low border border-border rounded-full"
                >
                  <span className="mr-2">←</span>
                  Back to Ingredients
                </button>
                <button
                  type="submit"
                  disabled={isGenerating || auth.loading || cloud.loading}
                  className="flex items-center justify-center px-4 py-3 text-sm font-semibold mm-action rounded-md shadow-soft"
                >
                  {isGenerating ? 'Generating Recipe...' : 'Create Recipe'}
                  {!isGenerating && <span className="ml-2" aria-hidden="true">→</span>}
                </button>
              </div>
            </div>
          </form>
        </div>
      </section>
    );
  }

  if (step === 3) {
    // Step 3: Results
    return (
      <section id="generator" className="py-6 bg-surface-container">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          {/* Header */}
          <div className="mb-6 text-left">
            <h2 className="text-3xl font-bold text-on-surface">Your Custom Recipe</h2>
            <p className="mt-3 text-lg text-on-surface-variant">
              Here's your personalized recipe based on your ingredients and preferences
            </p>
          </div>

          {/* Progress Indicator */}
          <div className="mb-6 flex w-full items-center justify-between">
            <div className="flex-1 h-0.5 bg-surface-container-highest"></div>
            <div className="flex items-center space-x-3">
              <div className="w-2 h-2 rounded-full bg-surface-container-low"></div>
              <div className="w-2 h-2 rounded-full bg-surface-container-low"></div>
              <div className="w-2 h-2 rounded-full bg-primary-container"></div>
              <span className="text-xs font-medium text-on-surface-variant">Step 3 of 3</span>
            </div>
            <div className="flex-1 h-0.5 bg-surface-container-highest"></div>
          </div>

          {generatedRecipe && (
            <div className="rounded-2xl border border-border bg-surface-container p-8 shadow-soft">
              <div className="mb-6">
                <h1 className="text-2xl font-bold text-on-surface">{generatedRecipe.name}</h1>
                <p className="mt-2 text-lg text-on-surface-variant">
                  {generatedRecipe.structuredRecipe?.description}
                </p>
              </div>

              <div className="grid gap-8 md:grid-cols-2">
                {/* Ingredients */}
                <div>
                  <h3 className="text-lg font-semibold text-on-surface mb-4">Ingredients</h3>
                  <ul className="space-y-2 text-on-surface-variant">
                    {generatedRecipe.ingredients.map((ing, index) => (
                      <li key={index} className="flex items-center">
                        <div className="flex h-5 w-5 items-center justify-center rounded-full bg-surface-container-high text-primary shrink-0">
                          •
                        </div>
                        <span className="ml-3">{ing}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Instructions & Nutrition */}
                <div className="space-y-6 rounded-2xl bg-surface-container p-4 sm:p-5">
                  <div>
                    <h3 className="text-lg font-semibold text-on-surface mb-4">Instructions</h3>
                    <ol className="list-decimal pl-5 space-y-2 text-on-surface-variant">{generatedRecipe.structuredRecipe?.instructions.map((instruction, index) => <li key={index}>{instruction}</li>)}</ol>
                  </div>

                  <div className="mt-6">
                    <h3 className="text-lg font-semibold text-on-surface mb-4">{nutritionLabel(generatedRecipe.structuredRecipe)} (per serving)</h3>
                    {generatedRecipe.structuredRecipe && <PartialNutritionNote recipe={generatedRecipe.structuredRecipe} />}
                    <div className="grid gap-4 sm:grid-cols-4 text-sm text-on-surface-variant">
                      <div>
                        <p className="text-outline">Calories</p>
                        <p className="text-2xl font-bold text-on-surface">{generatedRecipe.structuredRecipe?.intelligence ? <NutritionValue recipe={generatedRecipe.structuredRecipe} nutrient="calories" /> : generatedRecipe.nutrition.calories ?? 'Unknown'}</p>
                      </div>
                      <div>
                        <p className="text-outline">Protein</p>
                        <p className="text-2xl font-bold text-on-surface">{generatedRecipe.structuredRecipe?.intelligence ? <NutritionValue recipe={generatedRecipe.structuredRecipe} nutrient="protein" /> : formatNutrient(generatedRecipe.nutrition.protein, 'g')}</p>
                      </div>
                      <div>
                        <p className="text-outline">Carbs</p>
                        <p className="text-2xl font-bold text-on-surface">{generatedRecipe.structuredRecipe?.intelligence ? <NutritionValue recipe={generatedRecipe.structuredRecipe} nutrient="carbohydrates" /> : formatNutrient(generatedRecipe.nutrition.carbs, 'g')}</p>
                      </div>
                      <div>
                        <p className="text-outline">Fat</p>
                        <p className="text-2xl font-bold text-on-surface">{generatedRecipe.structuredRecipe?.intelligence ? <NutritionValue recipe={generatedRecipe.structuredRecipe} nutrient="fat" /> : formatNutrient(generatedRecipe.nutrition.fat, 'g')}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {generatedRecipe.structuredRecipe?.intelligence ? <RecipeIntelligence recipe={generatedRecipe.structuredRecipe} /> :
                <p className="mt-6 text-sm text-on-surface-variant">AI estimates only. Nutrition, dietary tags and allergens have not been independently verified. Check ingredients and product labels.</p>}
              <p className="mt-2 text-sm text-on-surface-variant">Cuisine: {generatedRecipe.structuredRecipe?.cuisine}. Total time: {generatedRecipe.structuredRecipe?.total_time} mins</p>
              <p className="mt-2 text-sm text-on-surface-variant">Suggested dietary tags: {generatedRecipe.structuredRecipe?.dietary_tags.join(', ') || 'None reported'}</p>
              <p className="mt-2 text-sm text-on-surface-variant">Potential allergens: {generatedRecipe.structuredRecipe?.potential_allergens.join(', ') || 'None reported; absence is not verified'}</p>
              {onOpenRecipe && <button onClick={() => generatedRecipe.structuredRecipe && onOpenRecipe(generatedRecipe.structuredRecipe)} className="mt-4 rounded-2xl border border-border px-4 py-3 font-semibold">View Recipe Details</button>}
              {/* Additional Info */}
              <div className="mt-8 pt-6 border-t border-border">
                <div className="grid gap-4 sm:grid-cols-3 text-center">
                  <div>
                    <p className="text-outline">Prep Time</p>
                    <p className="text-xl font-bold text-on-surface">{generatedRecipe.prepTime}</p>
                  </div>
                  <div>
                    <p className="text-outline">Cook Time</p>
                    <p className="text-xl font-bold text-on-surface">{generatedRecipe.cookTime}</p>
                  </div>
                  <div>
                    <p className="text-outline">Servings</p>
                    <p className="text-xl font-bold text-on-surface">{generatedRecipe.servings}</p>
                  </div>
                  <div>
                    <p className="text-outline">Difficulty</p>
                    <p className="text-xl font-bold text-on-surface">{generatedRecipe.difficulty}</p>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="mt-8 pt-6 border-t border-border">
                <div className="flex justify-between">
                  <button
                    onClick={handleReset}
                    className="flex-1 px-4 py-3 text-sm font-medium text-on-surface-variant bg-surface-container hover:bg-surface-container-low border border-border rounded-full mr-2"
                  >
                    <span className="mr-2">↺</span>
                    Start Over
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        await cloud.save(generatedRecipe);
                        onNavigate('saved');
                      } catch (error) {
                        setSaveError((error as Error).message);
                      }
                    }}
                    className="flex-1 px-4 py-3 text-sm font-semibold mm-action rounded-md shadow-soft ml-2"
                  >
                    Save Recipe
                  </button>
                </div>
                {saveError && <p role="alert" className="mt-3 text-sm text-error">{saveError}</p>}
              </div>
            </div>
          )}

          {/* Empty state (shouldn't happen normally) */}
          {!generatedRecipe && (
            <div className="text-center py-6">
              <h3 className="text-xl font-bold text-on-surface mb-4">No Recipe Generated</h3>
              <p className="text-lg text-on-surface-variant">
                Something went wrong. Please try again.
              </p>
              <button
                onClick={handleReset}
                className="mt-6 px-6 py-3 text-sm font-semibold mm-action rounded-md shadow-soft"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      </section>
    );
  }

  return null; // Should never reach here
};

export default RecipeGenerator;
