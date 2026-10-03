import { DesignHeader, DesignNav } from './components/DesignShell';
import Pantry from './components/Pantry';
import KitchenHome from './components/KitchenHome';
import { AuthProvider, useAuth } from './AuthContext';
import { UserDataProvider } from './UserDataContext';
import { GeneratedRecipe } from './recipeApi';
import React, { useEffect, useRef, useState } from 'react';

import RecipeGenerator from './components/RecipeGenerator';
import RecipeResults from './components/RecipeResults';
import RecipeDetail from './components/RecipeDetail';
import IngredientScanner from './components/IngredientScanner';
import MealAnalyzer from './components/MealAnalyzer';
import SavedRecipes from './components/SavedRecipes';
import Profile from './components/Profile';

import PasswordRecovery from './components/PasswordRecovery';

const sections = ['home', 'generator', 'results', 'detail', 'scanner', 'analyzer', 'saved', 'discover', 'profile', 'pantry'];
const readSection = () => sections.includes(window.location.hash.slice(1)) ? window.location.hash.slice(1) : 'home';

export function AppContent() {
  const { user, recovering } = useAuth();
  const [passwordUpdated, setPasswordUpdated] = useState(false);
  useEffect(() => { setPasswordUpdated(false); }, [user?.id]);
  useEffect(() => { if (recovering) setPasswordUpdated(false); }, [recovering]);
  const previousUser = useRef(user?.id);

  const [latestRecipe, setLatestRecipe] = useState<GeneratedRecipe | null>(null);
  const [detailRecipe, setDetailRecipe] = useState<GeneratedRecipe | null>(null);
  const [scannerIngredients, setScannerIngredients] = useState<string[]>([]);
  const openRecipe = (recipe: GeneratedRecipe) => { setDetailRecipe(recipe); navigateTo('detail'); };
  useEffect(() => {
    if (previousUser.current && previousUser.current !== user?.id) {
      setLatestRecipe(null);
      setDetailRecipe(null);
    }
    previousUser.current = user?.id;
  }, [user?.id]);
  const [currentSection, setCurrentSection] = useState<string>(readSection);

  // Handle navigation
  const navigateTo = (section: string) => {
    if (!sections.includes(section)) return;
    setScannerIngredients([]);
    window.location.hash = section;
    setCurrentSection(section);

  };

  useEffect(() => {
    const syncSection = () => { setCurrentSection(readSection()); };

    window.addEventListener('hashchange', syncSection);

    return () => { window.removeEventListener('hashchange', syncSection); };
  }, []);

  useEffect(() => {
    document.title = `MealMind · ${currentSection.charAt(0).toUpperCase() + currentSection.slice(1)}`;
    window.scrollTo(0, 0);
  }, [currentSection]);

  return (
    <div className="App min-h-screen bg-surface text-on-surface antialiased">
      <DesignHeader navigate={navigateTo} />
      <main id="main-content" className="mm-content pt-20 pb-28 max-w-4xl mx-auto">
            {passwordUpdated && <p role="status">Password updated successfully. You are signed in.</p>}
            {recovering ? <PasswordRecovery onComplete={() => { setPasswordUpdated(true); navigateTo('profile'); }} /> : <>
            {/* Content based on current section */}
            {(currentSection === 'home' || currentSection === 'discover') && <KitchenHome onNavigate={navigateTo} />}
            {currentSection === 'generator' && <RecipeGenerator initialIngredients={scannerIngredients} onNavigate={navigateTo} onGenerated={setLatestRecipe} onOpenRecipe={openRecipe} />}
            {currentSection === 'results' && <RecipeResults onNavigate={navigateTo} generatedRecipe={latestRecipe} onOpenRecipe={openRecipe} onRecipeUpdated={setLatestRecipe} />}
            {currentSection === 'detail' && <RecipeDetail key={detailRecipe?.id || "empty"} onNavigate={navigateTo} generatedRecipe={detailRecipe} onRecipeUpdated={setDetailRecipe} />}
            {currentSection === 'scanner' && <IngredientScanner onNavigate={navigateTo} onCreateRecipe={names => { navigateTo('generator'); setScannerIngredients(names); }} />}
            {currentSection === 'analyzer' && <MealAnalyzer onNavigate={navigateTo} />}
            {currentSection === 'saved' && <SavedRecipes onNavigate={navigateTo} onOpenRecipe={openRecipe} />}
            {currentSection === 'profile' && <Profile onNavigate={navigateTo} />}
            {currentSection === 'pantry' && <Pantry onNavigate={navigateTo} onOpenRecipe={openRecipe} />}
            </>}
      </main>
      <DesignNav section={currentSection} navigate={navigateTo} />
    </div>
  );
}

export default function App() { return <AuthProvider><UserDataProvider><AppContent /></UserDataProvider></AuthProvider>; }
