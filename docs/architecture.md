# Architecture

React owns presentation and transient review state. FastAPI services own validation, calculation and orchestration. Supabase Auth verifies identity; repositories use the caller JWT/public project key, with database RLS as the final ownership boundary.

## Recipes and nutrition

Generation merges saved restrictions with the request, asks Gemini for a structured proposal, validates it locally, normalizes ingredients and invokes NutritionService. USDA identity/state/portion matching is conservative. Nutrition retains coverage/provenance and missing values stay null. ConstraintService uses calculated evidence, not AI assertions that goals passed.

Recipe Repair is user-triggered. A dedicated service receives failed checks, requests a structured proposal, then repeats normalization, calculation and validation. At most two attempts follow the original. Deterministic normalized violation scoring selects eligible results; hard restrictions are not exchanged for macro improvements. The original remains accessible.

## Pantry and substitutions

Pantry stores owner-scoped identities with optional quantities. Compatibility separates presence from sufficient quantity and retains unknowns in coverage denominators. It does not invent density or piece weights. Recommendations rank the account's saved recipes by documented pantry coverage rather than fabricating a public recipe corpus.

The substitution catalog has directed relationships and explicit cooking contexts. Browse is deterministic. Preview changes one selected ingredient and independently evaluates both versions. Unknown hard compatibility prevents adopting a preview; unknown ratios require user-supplied amounts. Use is always explicit.

## Vision and persistence

Scanner and Analyzer share bounded image handling but have separate proposal/review contracts. A local preview is not automatically analyzed. The user explicitly sends a cleaned image for structured recognition. Scanner requires reviewed confirmation before Pantry/Studio actions. Analyzer requires reviewed components and quantities before calculation. MealMind does not permanently store photos.

Profiles, preferences, saved snapshots and Pantry use owner policies. Frontend account-change guards discard stale responses. Ordinary operations never use privileged database credentials. Migrations are in `supabase/migrations/`.

Provider deadlines, bounded retries, response caps and per-process admission limit work but do not replace shared deployment controls. [Evaluation](evaluation.md) distinguishes synthetic pipeline regression from opted-in live measurements.
