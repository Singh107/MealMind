# MealMind

MealMind is a full-stack food-intelligence application combining generative AI, structured food data, deterministic constraint checks, pantry matching and human-reviewed computer vision.

## Live demo

Deployment pending. No public demo is currently provided.

## Screenshots

Clean screenshots of Recipe Studio, recipe nutrition/constraints, Pantry and photo review are planned. See the [screenshot checklist](docs/screenshots.md). No personal-account screenshots are included.

## Why MealMind

Generating a plausible recipe is different from checking its nutrition or dietary restrictions. MealMind separates AI proposals from independently calculated results. Gemini produces structured recipes and recognition suggestions; validated quantities and matched USDA records determine calculated nutrition. Constraint checks retain **passed**, **failed** and **unknown** outcomes. Missing evidence is never treated as zero or proof of safety.

## Features

- Recipe generation with saved preferences, dietary restrictions, exclusions and nutrition goals.
- USDA-backed nutrition with ingredient provenance and explicit partial/unavailable coverage.
- Independent constraint validation and user-triggered Recipe Repair with bounded attempts and deterministic selection.
- Account-owned Pantry, conservative ingredient/quantity matching and pantry-aware ranking of saved recipes.
- Curated, context-specific substitutions with explicit preview and independent recalculation.
- Ingredient Scanner with editable recognition suggestions and confirmation before Pantry/Studio actions.
- Meal Analyzer with reviewed components and user-supplied quantities before nutrition calculation.
- Saved recipes, preferences, Supabase authentication, session restoration and password recovery.

## Architecture

```text
User preferences / Pantry / Photo
                |
         React + TypeScript
                |
            FastAPI
                |
    Gemini structured proposals
                |
      Ingredient normalization
                |
    USDA matching + quantity calculation
                |
       Constraint validation
                |
    Recipe result / bounded repair

Pantry and substitution services reuse normalization and validation.
Supabase Auth verifies identity; owner-scoped Postgres RLS protects saved data.
Persistence occurs through explicit user actions, not every AI response.
```

AI nutrition estimates are not authoritative. Pantry browsing and substitution discovery are deterministic and do not require AI calls. See [architecture](docs/architecture.md) for the distinct workflows.

## Human-in-the-loop design

Scanner proposes ingredient names. The user edits and confirms them before choosing a Pantry or Recipe Studio action. Meal Analyzer proposes meal components; the user reviews them and supplies quantities before requesting nutrition. A photo cannot establish weight, allergens, freshness or food safety. Neither flow silently stores the image or automatically generates/saves a recipe.

## Tech stack

| Layer | Technologies |
| --- | --- |
| Frontend | React, TypeScript, Tailwind CSS, Create React App |
| Backend | Python, FastAPI, Pydantic, HTTPX, Pillow |
| Accounts/data | Supabase Auth, PostgreSQL, row-level security |
| AI/food records | Gemini API, USDA FoodData Central |
| Verification | Python unittest, Jest/React Testing Library, Node build guards, deterministic evaluation tooling |

## Security and privacy

Provider secrets stay on the backend. Account APIs verify bearer identity and use caller-scoped Supabase requests under RLS. Uploaded images are bounded, decoded, re-encoded and stripped of metadata; MealMind does not permanently store them. The external vision provider still receives the sanitized image when analysis is requested.

Production configuration guards, body limits, provider deadlines, bounded responses and per-process rate/concurrency controls are implemented. Shared edge limits, production headers and deployment review are still required. This is not a claim of complete security or allergy safety. Read [security](docs/security.md) and [dependency status](docs/dependencies.md).

## Local development

Prerequisites: Python 3.13 and Node 24 are the verification versions; npm and Git are required. Run backend and frontend in separate terminals. These commands use PowerShell on Windows.

```powershell
# Terminal 1, from the repository root
cd backend
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env locally with your own configuration.
venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2, from the repository root
cd frontend
npm.cmd ci --ignore-scripts
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Configure public Supabase settings for account features.
$env:HOST='127.0.0.1'
npm.cmd start
```

On macOS/Linux, use `python3`, `venv/bin/python`, `npm` and equivalent shell environment/copy commands. The API health endpoint is `http://127.0.0.1:8000/health`; the frontend is `http://127.0.0.1:3000`. Health confirms reachability, not provider availability. Keep the development server local; it is not a production host.

Account features require a Supabase project with `supabase/migrations/` applied in filename order. Configure local Auth Site URL/redirects for your frontend and the intended sign-in method. Use only the public publishable/anon key in the application. Never run migrations against a database you do not intend to configure. The SQL ownership exercise in `supabase/tests/` is a separately invoked development-database check, not part of offline CI.

## Environment variables

Start with [backend/.env.example](backend/.env.example) and [frontend/.env.example](frontend/.env.example). Never commit populated local copies.

- `GEMINI_API_KEY` and `USDA_API_KEY`: backend-only secrets.
- `SUPABASE_URL` / `SUPABASE_ANON_KEY`: public project configuration used by the backend alongside the verified caller token.
- `REACT_APP_API_URL`, `REACT_APP_SUPABASE_URL`, `REACT_APP_SUPABASE_ANON_KEY`: browser-public values only; no other `REACT_APP_*` variables are approved.
- Production requires `MEALMIND_ENVIRONMENT=production`, public HTTPS origins/hosts, configured providers and mock mode disabled. The deployment factory refuses development mode.

Restart processes after configuration changes. Frontend production values are embedded during build. No service-role key, database admin credential or verification-user password is needed for ordinary use.

## Testing

```powershell
# From backend
venv/Scripts/python.exe -m unittest discover -s tests
venv/Scripts/python.exe -m evaluation --mode fixture

# From frontend
$env:CI='true'
npm.cmd test -- --watchAll=false --runInBand
node --test scripts/validate-env.test.cjs
```

For offline compilation use non-secret, nonfunctional placeholders:

```powershell
# From frontend; never deploy this placeholder build.
$env:REACT_APP_API_URL='https://api.example.invalid'
$env:REACT_APP_SUPABASE_URL='https://project.example.invalid'
$env:REACT_APP_SUPABASE_ANON_KEY='sb_publishable_ci_placeholder'
npm.cmd run build
```

Current verified baseline (October 3, 2026): **303 backend tests**, **189 frontend tests across 17 suites**, **4 build-guard tests**, and a passing production build. These are verification results, not permanent guarantees. CI repeats offline tests and compilation without provider credentials or live account mutations. See [evaluation](docs/evaluation.md) for what synthetic results measure.

## Known limitations

- Nutrition depends on food-record and portion matches; some ingredients/nutrients remain partial or unresolved.
- Substitutions are curated and context-specific, not universal cooking equivalences.
- Pantry presence does not prove sufficient quantity; piece-to-weight conversion is intentionally not guessed.
- Vision confidence is uncalibrated and requires user review.
- Neither dietary checks nor photos certify allergy safety or cross-contact absence.
- The CRA/react-scripts development/build toolchain has **29 documented audit findings**. Do not expose its development server or give untrusted builds credentials. Toolchain migration is separate work.

## Deployment

Deployment is pending. The intended architecture is a static HTTPS frontend, separately hosted FastAPI API and Supabase. Host/proxy trust, shared limits, provider quotas, CSP, recovery redirects and RLS must be verified before public exposure. No deployment workflow is included.

## License and assets

MealMind is licensed under the [MIT License](LICENSE). The local brand mark and decorative graphic were created for MealMind; externally hosted fonts retain their own licenses. See [asset provenance and attribution](docs/assets.md).
