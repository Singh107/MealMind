import React from 'react';
import { useAuth } from '../AuthContext';
import { useUserData } from '../UserDataContext';
import { APP_ASSETS } from '../designAssets';

export function Icon({ children }: { children: string }) { return <span aria-hidden="true" className="material-symbols-outlined">{children}</span>; }

export function DesignHeader({ navigate }: { navigate: (page: string) => void }) {
  const { user } = useAuth();
  const { displayName } = useUserData();
  return <header className="mm-header fixed top-0 w-full z-40 bg-surface-container/90 backdrop-blur-xl border-b border-border">
    <div className="h-16 px-4 md:px-6 flex items-center justify-between gap-2 max-w-4xl mx-auto">
      <button onClick={() => navigate('home')} className="flex min-h-11 min-w-0 items-center gap-2.5" aria-label="MealMind home">
        <img src={APP_ASSETS.logo} alt="" className="h-8 w-8 object-contain" />
        <span className="font-headline-sm">MealMind</span><span className="mm-header-badge rounded-full bg-primary-container text-secondary px-2 py-1 font-label-sm">AI KITCHEN</span>
      </button>
      <button aria-label={user ? 'Open profile' : 'Sign in'} onClick={() => navigate('profile')} className="w-11 h-11 shrink-0 rounded-full border border-secondary/30 bg-surface-container-high text-secondary flex items-center justify-center">
        {user ? <span aria-hidden="true">{(displayName || user.email || 'M').slice(0, 1).toUpperCase()}</span> : <Icon>person</Icon>}
      </button>
    </div>
  </header>;
}

export function DesignNav({ section, navigate }: { section: string; navigate: (page: string) => void }) {
  const { user } = useAuth(); const { recipes } = useUserData();
  return <nav aria-label="Main navigation" className="mm-nav fixed bottom-0 w-full z-40 px-2 pb-[max(.5rem,env(safe-area-inset-bottom))] pointer-events-none">
    <div className="pointer-events-auto max-w-lg mx-auto min-h-16 rounded-full bg-surface-container/95 backdrop-blur-2xl p-1.5 flex items-center justify-around shadow-soft border border-border">
      {[['home','Home','auto_awesome'],['pantry','Pantry','kitchen'],['generator','Studio','soup_kitchen'],['scanner','Scanner','document_scanner'],['analyzer','Analyzer','shield_with_heart'],['saved','Saved','bookmark']].map(([id,label,icon]) =>
        <button key={id} aria-label={label} aria-current={section === id ? 'page' : undefined} onClick={() => navigate(id)}
          className={`relative flex flex-col items-center justify-center min-w-[44px] px-2 py-1.5 rounded-full ${section === id ? 'text-secondary bg-primary-container ' : 'text-outline hover:text-on-surface'}`}>
          <Icon>{icon}</Icon><span className="text-[10px] sm:text-xs">{label}</span>
          {id === 'saved' && user && recipes.length > 0 && <span className="absolute -top-1 right-0 bg-secondary text-on-secondary rounded-full text-[9px] px-1">{recipes.length}</span>}
        </button>)}
    </div>
  </nav>;
}
