import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { useAuth } from './AuthContext';
import { accountRequest, createSaved, deleteSaved, emptyPreferences, getPreferences, listSaved, putPreferences, SavedRow, UserPreferences } from './accountApi';
import { SavedRecipe } from './recipeStorage';

const required = async (): Promise<any> => { throw new Error('Sign in to save recipes and access your account.'); };
interface UserData {
  recipes: SavedRow[]; preferences: UserPreferences; displayName: string; loading: boolean; error: string;
  save: (recipe: Omit<SavedRecipe, 'savedAt'> & { savedAt?: string }) => Promise<void>;
  remove: (id: string) => Promise<void>; reload: () => Promise<void>;
  savePreferences: (preferences: UserPreferences) => Promise<void>;
  saveProfile: (displayName: string) => Promise<void>;
}
const initial: UserData = { recipes: [], preferences: emptyPreferences, displayName: '', loading: false, error: '',
  save: required, remove: required, reload: required, savePreferences: required, saveProfile: required };
export const UserDataContext = createContext<UserData>(initial);
export const useUserData = () => useContext(UserDataContext);
export function UserDataProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const id = user?.id;
  const currentId = useRef(id); currentId.current = id;
  const [state, setState] = useState({ ...initial, owner: id });
  const reload = async () => {
    if (!id) return;
    const owner = id;
    setState(previous => ({ ...previous, loading: true, error: '' }));
    try {
      const [recipes, preferences, profile] = await Promise.all([listSaved(), getPreferences(), accountRequest<{ display_name: string }>('/api/profile')]);
      if (currentId.current === owner) setState(previous => ({ ...previous, owner, recipes, preferences, displayName: profile.display_name, loading: false }));
    } catch (error) {
      if (currentId.current === owner) setState(previous => ({ ...previous, owner, loading: false, error: (error as Error).message }));
    }
  };
  useEffect(() => {
    setState({ ...initial, owner: id, loading: !!id });
    void reload();
    // Reload only when account identity changes, not on token refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  const assertUser = () => { if (!id || currentId.current !== id) throw new Error('Sign in to save recipes and access your account.'); };
  const save: UserData['save'] = async recipe => {
    assertUser(); const row = await createSaved(recipe, id);
    if (currentId.current === id) setState(s => ({ ...s, recipes: [row, ...s.recipes.filter(r => r.id !== row.id)] }));
  };
  const remove = async (recipeId: string) => {
    assertUser(); await deleteSaved(recipeId, id);
    if (currentId.current === id) setState(s => ({ ...s, recipes: s.recipes.filter(r => r.id !== recipeId) }));
  };
  const savePreferences = async (preferences: UserPreferences) => {
    assertUser(); const saved = await putPreferences(preferences, id);
    if (currentId.current === id) setState(s => ({ ...s, preferences: saved }));
  };
  const saveProfile = async (displayName: string) => {
    assertUser(); await accountRequest('/api/profile', 'PUT', { display_name: displayName }, id);
    if (currentId.current === id) setState(s => ({ ...s, displayName }));
  };
  const visible = state.owner === id ? state : { ...initial, loading: !!id };
  return <UserDataContext.Provider value={{ ...visible, save, remove, reload, savePreferences, saveProfile }}>{children}</UserDataContext.Provider>;
}
