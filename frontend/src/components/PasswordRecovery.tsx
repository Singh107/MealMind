import React, { useState } from 'react';
import { useAuth } from '../AuthContext';

export default function PasswordRecovery({ onComplete }: { onComplete: () => void }) {
  const { updatePassword } = useAuth();
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <section className="mx-auto max-w-lg space-y-5 rounded-2xl border border-border p-8">
    <h1 className="text-3xl font-bold">Set new password</h1>
    <p>Choose a new password for your MealMind account.</p>
    {error && <p role="alert">{error}</p>}
    <form className="space-y-4" onSubmit={async event => {
      event.preventDefault();
      if (busy) return;
      if (password !== confirmation) { setError('Passwords do not match.'); return; }
      if (password.length < 6) { setError('Use at least 6 characters.'); return; }
      setBusy(true); setError('');
      try { await updatePassword(password); setPassword(''); setConfirmation(''); onComplete(); }
      catch (failure) { setError((failure as Error).message); }
      finally { setPassword(''); setConfirmation(''); setBusy(false); }
    }}>
      <label className="block">New password<input className="block w-full rounded-xl border p-3" type="password" autoComplete="new-password" minLength={6} required disabled={busy} value={password} onChange={e => setPassword(e.target.value)} /></label>
      <label className="block">Confirm new password<input className="block w-full rounded-xl border p-3" type="password" autoComplete="new-password" minLength={6} required disabled={busy} value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
      <button disabled={busy} className="rounded-xl mm-action px-5 py-3">{busy ? 'Updating password…' : 'Update password'}</button>
    </form>
  </section>;
}
