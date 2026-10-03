// Test-only repository boundary; production never imports this module.
import React, { useState } from 'react';
import { AuthContext, AuthState } from './AuthContext';
import { UserDataContext } from './UserDataContext';
import { emptyPreferences, SavedRow } from './accountApi';
import { SavedRecipe } from './recipeStorage';

export function testAccount() {
  const store = { rows: [] as SavedRow[], failSave: false };
  const auth: AuthState = { user: { id: 'test-user', email: 'test@example.com' } as any, accessToken: 'test-token',
    recovering: false, updatePassword: jest.fn(), signedIn: true, loading: false, error: '', signIn: jest.fn(), signUp: jest.fn(), signOut: jest.fn() };
  function Provider({ children }: { children: React.ReactNode }) {
    const [rows, setRows] = useState(store.rows);
    const [preferences, setPreferences] = useState(emptyPreferences);
    const [displayName, setDisplayName] = useState('Test User');
    return <AuthContext.Provider value={auth}><UserDataContext.Provider value={{ recipes: rows, preferences,
      displayName, loading: false, error: '', reload: jest.fn(),
      saveProfile: async name => { setDisplayName(name); }, savePreferences: async p => { setPreferences(p); },
      save: async value => {
        if (store.failSave) throw new Error('Account storage is unavailable.');
        const row = { id: value.id, source_id: value.structuredRecipe?.recipe_version_id || value.id,
          recipe: JSON.parse(JSON.stringify({ ...value, savedAt: value.savedAt || '2026-09-14' })) as SavedRecipe, created_at: '2026-09-14' };
        store.rows = [row, ...store.rows.filter(r => r.source_id !== row.source_id)]; setRows(store.rows);
      }, remove: async id => { store.rows = store.rows.filter(r => r.id !== id); setRows(store.rows); },
    }}>{children}</UserDataContext.Provider></AuthContext.Provider>;
  }
  return { store, auth, Provider };
}
