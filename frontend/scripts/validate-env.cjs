// Build-time boundary: only these deliberately public values may enter CRA bundles.
function validate(env) {
  const allowed = new Set(['REACT_APP_API_URL','REACT_APP_SUPABASE_URL','REACT_APP_SUPABASE_ANON_KEY']);
  for (const name of Object.keys(env)) {
    if (name.startsWith('REACT_APP_') && !allowed.has(name)) {
      throw new Error(
        'Unexpected REACT_APP_ variable. Only approved public configuration may enter the bundle.'
      );
    }
  }
  for (const name of ['REACT_APP_API_URL','REACT_APP_SUPABASE_URL']) {
    let url;
    try { url = new URL(env[name]); } catch { throw new Error(`${name} requires an explicit HTTPS production URL.`); }
    if (url.protocol !== 'https:' || ['localhost','127.0.0.1','[::1]'].includes(url.hostname) || url.username || url.password || url.search || url.hash)
      throw new Error(`${name} requires an HTTPS public URL without credentials, query or fragment.`);
  }
  const key = env.REACT_APP_SUPABASE_ANON_KEY || '';
  let publicKey = key.startsWith('sb_publishable_');
  try { publicKey ||= JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString()).role === 'anon'; } catch {}
  if (!publicKey || key.startsWith('sb_secret_')) throw new Error('Supabase browser configuration requires a public publishable/anon key.');
}
module.exports = { validate };
if (require.main === module) {
  process.env.NODE_ENV = 'production';
  require('react-scripts/config/env');
  try { validate(process.env); } catch (error) { console.error(error.message); process.exit(1); }
}
