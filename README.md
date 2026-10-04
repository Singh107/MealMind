# MealMind

**AI-powered food intelligence for personalized recipes, grounded nutrition, pantry-aware recommendations, ingredient scanning, and meal analysis.**

🌐 **Live Demo:** https://meal-mind-sand.vercel.app

> MealMind combines generative AI with structured food data and deterministic validation so that AI can handle reasoning and interpretation without being treated as the source of truth for nutritional facts.

---

## 📸 MealMind in Action

**[SCREENSHOT 1 — HERO]**

> **Add here:** One clean screenshot of MealMind's main Recipe Studio/home experience.  
> Try to have the interface populated rather than completely empty. This should be the best-looking screenshot because it is the first thing someone sees.

---

## What is MealMind?

MealMind is a full-stack food intelligence platform built to help users decide what to cook, understand what they're eating, and make better use of ingredients they already have.

A central design principle behind MealMind is that **generative AI and factual food data should have different responsibilities**.

Gemini handles tasks where reasoning and interpretation are useful, such as generating recipes and proposing ingredient recognition results. Structured USDA FoodData Central records are used for nutrition rather than relying on AI-generated estimates.

MealMind then independently normalizes ingredients, calculates nutrition, evaluates user constraints, and preserves uncertainty when evidence is incomplete.

---

## ✨ Features

### 🍳 Constraint-Aware Recipe Generation

Generate personalized recipes around saved preferences, dietary restrictions, ingredient exclusions, and nutrition goals.

Generated recipes are processed through MealMind's own normalization, nutrition, and constraint pipeline rather than treating the AI response as automatically correct.

**[SCREENSHOT 2 — RECIPE + NUTRITION]**

> **Add here:** Your best generated recipe screenshot. Ideally show the recipe plus some of its nutrition/constraint information.  
> If the full recipe requires scrolling, use **at most 2 screenshots** here.

---

### 🔧 Recipe Repair

When a generated recipe does not satisfy a user's requested constraints, MealMind can attempt to repair it instead of simply generating an unrelated recipe from scratch.

Repair attempts are bounded, independently recalculated, and evaluated against the original constraints before a result is selected.

This keeps the AI generation layer separate from the system responsible for determining whether a recipe actually satisfies the requested requirements.

---

### 🥫 Pantry Intelligence

MealMind allows users to maintain an account-owned pantry and uses normalized ingredient matching to understand which saved recipes can make use of ingredients they already have.

Pantry-aware ranking is deterministic and does not require another AI request just to determine ingredient overlap.

MealMind also avoids pretending to know more than the available data supports: having an ingredient in the pantry does not automatically prove that the user has enough of it to complete a recipe.

**[SCREENSHOT 3 — PANTRY]**

> **Add here:** Use one screenshot that shows your pantry populated with realistic ingredients.  
> If possible, capture pantry recommendations in the same screenshot. If that isn't possible, you can use **2 screenshots maximum** for this section.

---

### 🔄 Context-Aware Ingredient Substitutions

MealMind provides curated substitutions based on the context in which an ingredient is being used.

Users can preview substitutions before applying them, and affected nutrition and constraints can be independently recalculated rather than assuming a substitution is nutritionally equivalent.

---

### 📷 Ingredient Scanner

The Ingredient Scanner uses computer vision to propose ingredients from an uploaded image.

MealMind intentionally keeps a human in the loop. Recognition results are suggestions: users can review and edit detected ingredients before confirming what should be sent to their Pantry or Recipe Studio.

A photograph alone is never treated as proof of ingredient weight, freshness, allergens, cross-contact, or food safety.

**[SCREENSHOTS 4A + 4B — INGREDIENT SCANNER]**

> **Add here:** Use **2 screenshots**, not all three unless absolutely necessary.
>
> **4A:** The strongest recognition/review screen showing what MealMind identified.  
> **4B:** The confirmed result or Pantry/Recipe Studio action.
>
> You probably don't need a separate screenshot that only shows the original upload screen unless it adds something important.

---

### 🔍 Meal Analyzer

Meal Analyzer helps users break a meal into recognizable components before calculating nutrition.

Instead of pretending that a photograph can reveal exact quantities, MealMind asks users to review the proposed components and provide quantities before nutrition is calculated from structured food records.

This keeps image recognition separate from nutrition calculation and makes uncertainty visible to the user.

**[SCREENSHOTS 5A + 5B — MEAL ANALYZER]**

> **Add here:** These are the **2 screenshots you already took** showing the analyzed meal/results.  
> That's enough. You don't need another screenshot just to show the initial upload state.

---

## 🧠 Grounded AI Instead of AI Guesswork

MealMind was designed around a distinction between **generation** and **verification**.

Large language models are useful for generating and interpreting food information, but they are not authoritative nutrition databases. MealMind therefore assigns different responsibilities to different systems:

- **Gemini** → recipe generation, interpretation, and recognition proposals
- **USDA FoodData Central** → structured food and nutrition records
- **MealMind backend** → normalization, quantity calculations, constraint evaluation, reliability logic, and repair
- **Supabase** → authentication and persistent account data

Nutrition values are derived from matched structured records rather than asking Gemini to invent nutritional values.

When MealMind cannot resolve sufficient evidence, it preserves partial or unavailable results instead of silently treating missing information as zero.

---

## 🏗️ Architecture

```text
                     User
                       │
                       ▼
              React + TypeScript
                       │
                       ▼
                    FastAPI
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
       Gemini         USDA       Supabase
          │            │            │
     Generation /   Structured     Auth +
     Recognition    Food Data    Persistence
          │            │
          └──────┬─────┘
                 ▼
        Ingredient Normalization
                 │
                 ▼
        Nutrition Calculation
                 │
                 ▼
        Constraint Validation
                 │
                 ▼
        Reliability / Repair
```

Pantry browsing and substitution discovery reuse MealMind's normalization and validation systems and do not require unnecessary AI calls.

Supabase Auth verifies user identity, while owner-scoped PostgreSQL row-level security protects persisted user data.

Persistence happens through explicit user actions rather than automatically storing every AI response.

---

## 👤 Human-in-the-Loop AI

MealMind deliberately avoids treating AI output as unquestionable fact.

The Ingredient Scanner proposes ingredient identities, but users review and confirm them before taking Pantry or Recipe Studio actions.

Meal Analyzer similarly proposes meal components, while users review those components and supply quantities before requesting nutrition calculations.

A photo cannot reliably establish exact weight, allergens, freshness, cross-contact, or food safety. MealMind therefore keeps these limitations visible rather than hiding uncertainty behind an AI-generated answer.

---

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React, TypeScript, Tailwind CSS, Create React App |
| **Backend** | Python, FastAPI, Pydantic, HTTPX, Pillow |
| **Accounts & Data** | Supabase Auth, PostgreSQL, Row-Level Security |
| **AI & Food Data** | Google Gemini API, USDA FoodData Central |
| **Deployment** | Vercel, Render, Supabase |
| **Verification** | Python unittest, Jest, React Testing Library, build guards, deterministic evaluation tooling |

---

## 🔐 Security & Privacy

Provider credentials remain server-side and are never intentionally exposed through the frontend bundle.

Account APIs verify authenticated users, while persisted account data is protected through caller-scoped access and PostgreSQL row-level security.

Uploaded images are size-bounded, decoded, re-encoded, and stripped of metadata before analysis. MealMind does not permanently store uploaded images, although sanitized images are sent to the external vision provider when analysis is explicitly requested.

Production protections include configuration validation, request/body limits, provider deadlines, bounded responses, security headers, and rate/concurrency controls.

These protections are not a claim of complete security, medical accuracy, or allergy safety. See `SECURITY.md` for the project's complete security and dependency documentation.

---

## 🚀 Deployment

MealMind v1.0 is publicly deployed.

| Component | Platform |
|---|---|
| **Frontend** | Vercel |
| **Backend API** | Render |
| **Database & Auth** | Supabase |
| **AI** | Google Gemini |
| **Nutrition Data** | USDA FoodData Central |

🌐 **Live Application:** https://meal-mind-sand.vercel.app

The production backend validates required configuration at startup and rejects development mock mode. Frontend production builds also restrict browser-exposed environment variables to an explicit allowlist.

---

## 💻 Local Development

### Prerequisites

The currently verified development versions are:

- Python 3.13
- Node.js 24
- npm
- Git

Run the backend and frontend in separate terminals.

### Backend

```powershell
cd backend

python -m venv venv

venv/Scripts/python.exe -m pip install -r requirements.txt

if (!(Test-Path .env)) {
    Copy-Item .env.example .env
}

# Configure your local .env before starting.

venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend

npm.cmd ci --ignore-scripts

if (!(Test-Path .env)) {
    Copy-Item .env.example .env
}

# Configure public Supabase settings and the backend URL.

$env:HOST='127.0.0.1'

npm.cmd start
```

The local services are available at:

```text
Frontend: http://127.0.0.1:3000
Backend:  http://127.0.0.1:8000
Health:   http://127.0.0.1:8000/health
```

On macOS/Linux, use `python3`, `venv/bin/python`, `npm`, and the equivalent shell commands.

The development server should remain local and is not intended to serve as a production host.

---

## ⚙️ Environment Variables

Start with:

```text
backend/.env.example
frontend/.env.example
```

Never commit populated local `.env` files.

### Backend

```text
GEMINI_API_KEY
USDA_API_KEY
SUPABASE_URL
SUPABASE_ANON_KEY
```

Gemini and USDA credentials are backend-only secrets.

Production additionally requires the appropriate production environment, HTTPS origins/hosts, configured providers, and disabled development mock mode.

### Frontend

Only the following `REACT_APP_*` variables are approved:

```text
REACT_APP_API_URL
REACT_APP_SUPABASE_URL
REACT_APP_SUPABASE_ANON_KEY
```

Frontend production configuration is embedded during the build process.

No Gemini key, USDA key, Supabase service-role key, database administrator credential, or verification-user password should be exposed to the browser.

---

## 🧪 Testing

### Backend

```powershell
cd backend

venv/Scripts/python.exe -m unittest discover -s tests
venv/Scripts/python.exe -m evaluation --mode fixture
```

### Frontend

```powershell
cd frontend

$env:CI='true'

npm.cmd test -- --watchAll=false --runInBand
node --test scripts/validate-env.test.cjs
```

For offline compilation, non-secret and nonfunctional placeholder values can be used:

```powershell
$env:REACT_APP_API_URL='https://api.example.invalid'
$env:REACT_APP_SUPABASE_URL='https://project.example.invalid'
$env:REACT_APP_SUPABASE_ANON_KEY='sb_publishable_ci_placeholder'

npm.cmd run build
```

Never deploy the placeholder build.

The project's verified pre-deployment baseline included:

- **303 backend tests**
- **189 frontend tests across 17 suites**
- **4 build-guard tests**
- **Passing optimized production build**

These numbers describe a verification baseline rather than a permanent guarantee. CI performs offline verification without requiring production provider credentials or live account mutations.

---

## ⚠️ Known Limitations

MealMind intentionally exposes several limitations rather than hiding them behind AI-generated certainty:

- Nutrition accuracy depends on successful food-record and portion matching. Some ingredients or nutrients may remain partial or unresolved.
- Ingredient substitutions are curated and context-specific rather than universal cooking equivalences.
- Pantry presence does not prove sufficient quantity.
- Piece-to-weight conversion is intentionally not guessed when there is insufficient evidence.
- Vision confidence is not treated as calibrated certainty and requires user review.
- Photographs cannot establish exact quantity, freshness, allergens, cross-contact, or food safety.
- Dietary checks cannot certify allergy safety.
- The current CRA/react-scripts toolchain contains known dependency audit findings. Toolchain migration is considered separate future infrastructure work rather than something silently addressed through unsafe forced upgrades.

---

## 📱 Responsive Design

MealMind's interface is designed to remain usable across desktop and smaller screen sizes.

**[OPTIONAL SCREENSHOT 6 — MOBILE]**

> **Add here only if your mobile screenshot looks particularly good.**  
> If it doesn't add much beyond the desktop screenshots, skip it. Your README does not need a mobile screenshot just to prove one exists.

---

## 📄 License

MealMind is available under the **MIT License**.

The MealMind brand mark and decorative graphics were created for the project. Externally hosted fonts and third-party services retain their respective licenses and terms.

---

## 🙋 About the Project

MealMind was built as an exploration of how generative AI can be incorporated into a larger software system **without making the entire product dependent on AI-generated facts**.

Rather than treating an LLM response as the final answer, MealMind combines generative reasoning with structured data, deterministic validation, explicit uncertainty, human review, authentication, persistence, and production infrastructure.

The result is a food intelligence platform where AI is one component of the system—not the source of truth for everything.

---

### Try MealMind

🌐 **Live Demo:** https://meal-mind-sand.vercel.app

💻 **Source Code:** https://github.com/Singh107/MealMind

---

**MealMind v1.0 — built, tested, and deployed.**
