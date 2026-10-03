import { useAuth } from '../AuthContext';
import { useUserData } from '../UserDataContext';
import { UserPreferences, emptyPreferences } from '../accountApi';
import AuthPanel from './AuthPanel';
import React, { useEffect, useState } from 'react';

interface DietaryPreferences {
  vegetarian: boolean;
  vegan: boolean;
  glutenFree: boolean;
  dairyFree: boolean;
  nutAllergy: boolean;
}

interface ProfileProps {
  onNavigate: (section: string) => void;
}

const Profile: React.FC<ProfileProps> = ({ onNavigate }) => {
  const auth = useAuth();
  const cloud = useUserData();
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [allergyText, setAllergyText] = useState('');
  const [exclusionText, setExclusionText] = useState('');
  const [cuisineText, setCuisineText] = useState('');
  const [extraPreferences, setExtraPreferences] = useState<UserPreferences>(emptyPreferences);
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [savedProfile, setSavedProfile] = useState({ name: '', email: '' });


  const [dietaryPreferences, setDietaryPreferences] = useState<DietaryPreferences>({
    vegetarian: false,
    vegan: false,
    glutenFree: false,
    dairyFree: false,
    nutAllergy: false
  });


  useEffect(() => {
    setEditName(cloud.displayName); setEditEmail(auth.user?.email || '');
    setSavedProfile({ name: cloud.displayName, email: auth.user?.email || '' });
    setExtraPreferences(cloud.preferences);
    setAllergyText(cloud.preferences.allergies.filter(x => x !== 'nuts').join(', '));
    setExclusionText(cloud.preferences.excluded_ingredients.join(', '));
    setCuisineText(cloud.preferences.preferred_cuisines.join(', '));
    setDietaryPreferences({ vegetarian: cloud.preferences.dietary_preferences.includes('vegetarian'),
      vegan: cloud.preferences.dietary_preferences.includes('vegan'), glutenFree: cloud.preferences.dietary_preferences.includes('gluten-free'),
      dairyFree: cloud.preferences.dietary_preferences.includes('dairy-free'), nutAllergy: cloud.preferences.allergies.includes('nuts') });
  }, [cloud.displayName, cloud.preferences, auth.user?.email]);
  const handleSaveChanges = async () => {
    setBusy(true); setStatus('');
    try {
      const managed = ['vegetarian', 'vegan', 'gluten-free', 'dairy-free'];
      const dietary = extraPreferences.dietary_preferences.filter(value => !managed.includes(value));
      if (dietaryPreferences.vegetarian) dietary.push('vegetarian');
      if (dietaryPreferences.vegan) dietary.push('vegan');
      if (dietaryPreferences.glutenFree) dietary.push('gluten-free');
      if (dietaryPreferences.dairyFree) dietary.push('dairy-free');
      const splitNames = (text: string) => text.split(',').map(x => x.trim()).filter(Boolean);
      const allergies = splitNames(allergyText).filter(value => value !== 'nuts');
      if (dietaryPreferences.nutAllergy) allergies.push('nuts');
      await cloud.savePreferences({ ...extraPreferences, dietary_preferences: dietary, allergies, excluded_ingredients: splitNames(exclusionText), preferred_cuisines: splitNames(cuisineText) });
      await cloud.saveProfile(editName);
      setSavedProfile({ name: editName, email: editEmail }); setIsEditing(false);
      setStatus('Profile and preferences saved.');
    } catch (error) { setStatus((error as Error).message); }
    finally { setBusy(false); }
  };
  const handleSignOut = async () => {
    try { await auth.signOut(); } catch (error) { setStatus((error as Error).message); }
  };
  if (auth.loading) return <p role="status">Restoring session...</p>;
  if (!auth.signedIn) return <AuthPanel />;

  return <section id="profile" className="py-6">
    <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 space-y-5">
      <div className="flex flex-wrap items-center gap-3"><button className="mm-button mm-secondary" onClick={()=>window.history.back()}>Go back</button><h1 className="text-3xl font-bold">Your Profile</h1></div>
      {status && <p role="status" className="rounded-xl bg-surface-container-low p-4">{status}</p>}
      {cloud.error && <p role="alert">{cloud.error} <button onClick={() => void cloud.reload()}>Retry</button></p>}
      {cloud.loading && <p role="status">Loading account preferences...</p>}
      <section aria-label="Account" className="mm-panel space-y-4">
        <h2 className="text-xl font-semibold">Account</h2>
        <div className="flex flex-wrap items-center gap-4">
          <div aria-hidden="true" className="h-16 w-16 shrink-0 rounded-full bg-primary-container text-primary flex items-center justify-center text-2xl">{(editName || editEmail || 'M').slice(0,1).toUpperCase()}</div>
          <div className="min-w-0 flex-1 space-y-2">
            {isEditing ? <><label className="block">Name<input aria-label="Name" placeholder="Enter your name" className="block w-full rounded-xl border p-3" value={editName} onChange={e=>setEditName(e.target.value)} /></label>
              <label className="block">Account email<input type="email" aria-label="Account email" placeholder="Enter your email" className="block w-full rounded-xl border p-3" readOnly value={editEmail} /></label></>
              : <><h3 className="text-xl font-semibold">{editName || 'Your account'}</h3><p className="break-words text-sm text-on-surface-variant">{editEmail}</p></>}
            <p className="text-sm text-on-surface-variant">{cloud.recipes.length} Saved recipes</p>
          </div>
          {!isEditing ? <button className="mm-button mm-secondary" onClick={()=>setIsEditing(true)}>Edit Profile</button>
            : <button className="mm-button mm-secondary" onClick={()=>{setEditName(savedProfile.name);setEditEmail(savedProfile.email);setIsEditing(false);}}>Cancel</button>}
        </div>
      </section>
      <section className="mm-panel space-y-4" aria-label="Dietary preferences">
        <h2 className="text-xl font-semibold">Dietary preferences</h2>
        <div className="grid sm:grid-cols-2 gap-3">{([
          ['vegetarian','Vegetarian'],['vegan','Vegan'],['glutenFree','Gluten-Free'],['dairyFree','Dairy-Free'],['nutAllergy','Nut Allergy']
        ] as [keyof DietaryPreferences,string][]).map(([key,label])=><label key={key} className="mm-check-target flex items-center gap-3 rounded-xl bg-surface-container-low p-3">
          <input type="checkbox" checked={dietaryPreferences[key]} onChange={()=>setDietaryPreferences(p=>({...p,[key]:!p[key]}))} />{label}</label>)}</div>
      </section>
      <section className="mm-panel space-y-4" aria-label="Ingredients and cuisine">
        <h2 className="text-xl font-semibold">Ingredients & cuisine</h2>
        <p className="text-sm text-on-surface-variant">Separate multiple items with commas.</p>
        <label className="block">Other allergies (comma-separated)<input placeholder="e.g., sesame, shellfish" className="block w-full rounded-xl border p-3" value={allergyText} onChange={e=>setAllergyText(e.target.value)} /></label>
        <label className="block">Excluded ingredients (comma-separated)<input placeholder="e.g., mushrooms, olives" className="block w-full rounded-xl border p-3" value={exclusionText} onChange={e=>setExclusionText(e.target.value)} /></label>
        <label className="block">Preferred cuisines (comma-separated)<input placeholder="e.g., Indian, Mediterranean" className="block w-full rounded-xl border p-3" value={cuisineText} onChange={e=>setCuisineText(e.target.value)} /></label>
      </section>
      <section className="mm-panel space-y-4" aria-label="Nutrition targets">
        <h2 className="text-xl font-semibold">Nutrition targets</h2>
        <div className="grid sm:grid-cols-2 gap-4">{(['calorie_target','protein_target','carbs_target','fat_target'] as const).map((key,index)=><label className="block" key={key}>{['Maximum calories (kcal)','Minimum protein (g)','Maximum carbs (g)','Maximum fat (g)'][index]}
          <input className="block w-full rounded-xl border p-3" type="number" min="0" max={[2000,200,300,100][index]} value={extraPreferences.nutrition_targets[key] ?? ''} onChange={e=>setExtraPreferences(p=>({...p,nutrition_targets:{...p.nutrition_targets,[key]:e.target.value==='' ? null : Number(e.target.value)}}))} /></label>)}</div>
      </section>
      <div className="flex flex-wrap items-center gap-3"><button className="mm-button" disabled={busy || cloud.loading || !!cloud.error} onClick={handleSaveChanges}>{busy ? 'Saving...' : isEditing ? 'Save Changes' : 'Save preferences'}</button></div>
      <div className="border-t border-border pt-5"><button className="mm-button mm-secondary" onClick={handleSignOut}>Sign Out</button></div>
    </div>
  </section>;
};

export default Profile;
