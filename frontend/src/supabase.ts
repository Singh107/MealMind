import { createClient } from '@supabase/supabase-js';

const url = process.env.REACT_APP_SUPABASE_URL;
const key = process.env.REACT_APP_SUPABASE_ANON_KEY;
// Only public project settings belong in the browser. Never use a service-role key.
export const supabase = url && key ? createClient(url, key, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
}) : null;

// Register before React mounts: redirect processing can finish before its effects run.
let recoveryUserId: string | null = null;
supabase?.auth.onAuthStateChange((event, session) => {
  if (event === 'PASSWORD_RECOVERY') recoveryUserId = session?.user.id || null;
  else if (!session || session.user.id !== recoveryUserId) recoveryUserId = null;
});
export const isRecoverySession = (userId?: string) => !!userId && recoveryUserId === userId;
export const completeRecovery = () => { recoveryUserId = null; };
