const { test } = require('node:test');
const assert = require('node:assert/strict');
const { validate } = require('./validate-env.cjs');
const good = { REACT_APP_API_URL:'https://api.example.com',REACT_APP_SUPABASE_URL:'https://project.example.com',REACT_APP_SUPABASE_ANON_KEY:'sb_publishable_test' };
test('explicit public production values pass', () => assert.doesNotThrow(() => validate(good)));
test('localhost and absent production API fail', () => {
  for (const value of [undefined,'http://localhost:8000','https://localhost','https://user:password@example.com'])
    assert.throws(() => validate({...good,REACT_APP_API_URL:value}));
});
test('server key names cannot enter CRA', () => assert.throws(() => validate({...good,REACT_APP_GEMINI_API_KEY:'test'})));
test('service role keys fail without appearing in errors', () => {
  const secret='sb_secret_NEVER_ECHO_THIS';
  try { validate({...good,REACT_APP_SUPABASE_ANON_KEY:secret});assert.fail(); }
  catch (error) { assert.equal(error.message.includes(secret),false); }
});
