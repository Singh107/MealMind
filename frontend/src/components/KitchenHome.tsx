import React from 'react';
import { useAuth } from '../AuthContext';
import { useUserData } from '../UserDataContext';
import { APP_ASSETS } from '../designAssets';
import { Icon } from './DesignShell';

export default function KitchenHome({ onNavigate }: { onNavigate: (page: string) => void }) {
  const { user } = useAuth(); const cloud = useUserData();
  return <div className="mm-page space-y-6">
    <section className="space-y-2"><p className="mm-kicker flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-brand-highlight" />Your kitchen</p>
      <h1 className="font-headline-lg-mobile">{user && cloud.displayName ? `Welcome back, ${cloud.displayName}` : 'Welcome to your kitchen'}</h1>
      <p className="text-on-surface-variant">What’s cooking today?</p>
      {user && cloud.preferences.dietary_preferences.length > 0 && <button className="rounded-full bg-surface-container px-3 py-1 text-sm text-secondary" onClick={() => onNavigate('profile')}>{cloud.preferences.dietary_preferences.join(' · ')} · Edit preferences</button>}
    </section>
    <section className="grid grid-cols-2 gap-2 p-2 rounded-2xl bg-surface-container-low">
      <button className="rounded-xl bg-surface-container p-3 text-center" onClick={() => onNavigate('saved')}><strong className="block text-xl text-primary">{user ? cloud.loading ? '…' : cloud.error ? '—' : cloud.recipes.length : '—'}</strong><span className="text-xs text-on-surface-variant">Saved favorites</span></button>
      <button className="rounded-xl bg-surface-container p-3 text-center" onClick={() => onNavigate('profile')}><Icon>tune</Icon><span className="block text-xs text-on-surface-variant">{user ? 'Your preferences' : 'Sign in to sync'}</span></button>
    </section>
    <section className="space-y-3"><h2 className="mm-kicker text-outline">Create something</h2>
      <button aria-label="Create a recipe" onClick={() => onNavigate('generator')} className="group w-full text-left relative overflow-hidden rounded-2xl bg-surface-container-high p-5 hover:bg-surface-bright">
        <div className="absolute top-0 right-0 w-36 h-36 bg-gradient-to-bl from-brand-highlight/20 to-transparent rounded-bl-full" />
        <div className="flex justify-between"><span className="w-12 h-12 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center"><Icon>soup_kitchen</Icon></span><span className="font-label-sm text-accent uppercase">Recipe Studio</span></div>
        <h3 className="font-headline-sm mt-4">Create a Recipe</h3><p className="text-sm text-on-surface-variant mt-1">Your ingredients and preferences, with nutrition calculated from food data.</p>
        <span className="mt-4 flex justify-between text-sm text-secondary"><span>Review nutrition & targets</span><span className="text-primary">Generate →</span></span>
      </button>
      <div className="grid grid-cols-2 gap-3">{[['scanner','document_scanner','Scan ingredients','Identify ingredients from a photo, review the suggestions, and choose what to use.'],['analyzer','shield_with_heart','Analyze a meal','Identify foods from a meal photo, enter the portions you ate, and calculate nutrition from food data.']].map(([page,icon,title,text]) =>
        <button key={page} onClick={() => onNavigate(page)} className="text-left rounded-2xl bg-surface-container p-4 space-y-3 hover:bg-surface-container-high"><span className={`inline-flex rounded-lg ${page === 'scanner' ? 'bg-fresh-soft text-fresh' : 'bg-sky-soft text-sky'}`}><Icon>{icon}</Icon></span><span className="block font-headline-sm text-base">{title}</span><span className="block text-sm text-on-surface-variant">{text}</span><span className="block font-label-sm text-primary">{page === 'scanner' ? 'Scan ingredients →' : 'Analyze meal →'}</span></button>)}</div>
    </section>
    <section className="relative rounded-2xl overflow-hidden min-h-48 bg-surface-container">
      <img src={APP_ASSETS.kitchenDecoration} alt="" aria-hidden="true" className="absolute inset-0 w-full h-full object-cover opacity-10" />
      <div className="relative p-6 bg-gradient-to-r from-surface-container to-transparent"><p className="mm-kicker">Make it your own</p><h2 className="text-2xl font-bold mt-2">Good food starts with an idea.</h2><p className="mt-2 max-w-sm text-on-surface-variant">Start with what you have, set your targets, and see what can be verified.</p><button className="mm-button mt-4" onClick={() => onNavigate('generator')}>Open Recipe Studio</button><p className="text-xs text-outline mt-3">Decorative illustration, not a generated recipe.</p></div>
    </section>
  </div>;
}
