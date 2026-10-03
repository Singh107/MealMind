import React, { useState } from 'react';
import { useAuth } from '../AuthContext';

export default function AuthPanel() {
  const auth = useAuth();
  const [mode, setMode] = useState<'in' | 'up'>('in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  return <section className="mx-auto max-w-lg space-y-5 rounded-2xl border border-border p-8">
    <h1 className="text-3xl font-bold">{mode === 'in' ? 'Sign In' : 'Sign Up'}</h1>
    <p>Sign in to save recipes and keep your preferences across devices.</p>
    {auth.error && <p role="alert">{auth.error}</p>}
    {message && <p role="status">{message}</p>}
    <form className="space-y-4" onSubmit={async event => {
      event.preventDefault(); setBusy(true); setMessage('');
      try {
        if (mode === 'in') await auth.signIn(email, password);
        else if (await auth.signUp(email, password)) setMessage('Check your email to confirm your account, then sign in.');
        setPassword('');
      } catch (error) { setMessage((error as Error).message); }
      finally { setBusy(false); }
    }}>
      <label className="block">Email<input className="block w-full rounded-xl border p-3" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label className="block">Password<input className="block w-full rounded-xl border p-3" type="password" autoComplete={mode === 'in' ? 'current-password' : 'new-password'} minLength={6} required value={password} onChange={e => setPassword(e.target.value)} /></label>
      <button disabled={busy || auth.loading} className="rounded-xl mm-action px-5 py-3">{busy ? 'Please wait…' : mode === 'in' ? 'Sign In' : 'Sign Up'}</button>
    </form>
    <button onClick={() => { setMode(mode === 'in' ? 'up' : 'in'); setMessage(''); }}>{mode === 'in' ? 'Create an account' : 'Already have an account? Sign In'}</button>
  </section>;
}
