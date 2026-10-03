import React, { createContext, useContext, useEffect, useState } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase, isRecoverySession, completeRecovery } from './supabase';

const unavailable = async () => { throw new Error('Sign-in is not configured yet.'); };
export interface AuthState {
  user: User | null; accessToken: string | null; loading: boolean; signedIn: boolean;
  error: string; signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<boolean>; signOut: () => Promise<void>;
  recovering: boolean; updatePassword: (password: string) => Promise<void>;
}
const signedOut: AuthState = { user: null, accessToken: null, loading: false, signedIn: false,
  error: '', signIn: unavailable, signUp: unavailable, signOut: unavailable,
  recovering: false, updatePassword: unavailable };
export const AuthContext = createContext<AuthState>(signedOut);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(!!supabase);
  const [error, setError] = useState('');
  const [recoveryId, setRecoveryId] = useState<string | null>(null);
  useEffect(() => {
    if (!supabase) return;
    let active = true;
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, next) => {
      if (active) {
        setSession(next); setLoading(false);
        if (event === 'PASSWORD_RECOVERY') setRecoveryId(next?.user.id || null);
        else setRecoveryId(previous => next?.user.id === previous ? previous : null);
      }
    });
    supabase.auth.getSession().then(({ data, error: failure }) => {
      if (!active) return;
      setSession(data.session); setLoading(false);
      if (isRecoverySession(data.session?.user.id)) setRecoveryId(data.session!.user.id);
      if (failure) setError('Your session could not be restored. Please sign in again.');
    }).catch(() => { if (active) { setLoading(false); setError('Account service is unavailable.'); } });
    const expire = () => { setSession(null); setRecoveryId(null); completeRecovery(); setError('Your session expired. Please sign in again.'); };
    window.addEventListener('mealmind:auth-expired', expire);
    return () => { active = false; subscription.unsubscribe(); window.removeEventListener('mealmind:auth-expired', expire); };
  }, []);
  const signIn = async (email: string, password: string) => {
    if (!supabase) return unavailable();
    const { data, error: failure } = await supabase.auth.signInWithPassword({ email, password });
    if (failure) throw new Error(failure.status === 400 ? 'Email or password is incorrect, or email confirmation is required.' : 'Sign-in service is unavailable. Please try again.');
    setSession(data.session); setError('');
  };
  const signUp = async (email: string, password: string) => {
    if (!supabase) return unavailable();
    const { data, error: failure } = await supabase.auth.signUp({ email, password });
    if (failure) throw new Error('Sign-up failed. Check your email and password and try again.');
    setSession(data.session); setError('');
    return !data.session;
  };
  const signOut = async () => {
    if (!supabase) return unavailable();
    const { error: failure } = await supabase.auth.signOut();
    if (failure) throw new Error('Sign-out could not complete. Please try again.');
    setSession(null); setError('');
    setRecoveryId(null); completeRecovery();
  };
  const updatePassword = async (password: string) => {
    if (!supabase || !session || recoveryId !== session.user.id) throw new Error('Open a fresh password recovery link to continue.');
    try {
      const { error: failure } = await supabase.auth.updateUser({ password });
      if (failure) throw failure;
    } catch {
      throw new Error('Password could not be updated. Check the project password requirements and try again. If your link has expired, request a fresh recovery email.');
    }
    completeRecovery(); setRecoveryId(null); setError('');
  };
  return <AuthContext.Provider value={{ user: session?.user || null, accessToken: session?.access_token || null,
    signedIn: !!session, loading, error, signIn, signUp, signOut,
    recovering: !!session && recoveryId === session.user.id, updatePassword }}>{children}</AuthContext.Provider>;
}
