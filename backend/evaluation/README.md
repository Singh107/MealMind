# Recipe pipeline evaluation

This CLI is offline tooling, separate from application routes and accounts. Fixture results measure pipeline regression, not Gemini quality or USDA measurements.

## Commands

From `backend`:

```powershell
venv/Scripts/python.exe -m evaluation --mode fixture
venv/Scripts/python.exe -m evaluation --case ordinary --limit 1 --output evaluation/results/single
venv/Scripts/python.exe -m unittest tests.test_evaluation
```

The default suite has 24 synthetic scenarios. Output is JSON plus Markdown under the selected stem; `evaluation/results/` is ignored. Exit 1 means a failed fixture regression expectation; exit 2 means invalid arguments/setup. An expected negative scenario can meet its regression expectation without being a successful recipe.

Live evaluation is separately opted in:

```powershell
venv/Scripts/python.exe -m evaluation --mode live --case ordinary --limit 1 --acknowledge-live-cost --output evaluation/results/live-smoke
```

This command is not run by CI. It uses configured real Gemini/USDA providers, prints its call budget and may incur costs. Execution is sequential, 1-25 cases, with existing provider deadlines and at most two HTTP attempts per generation. No extra evaluator retries, repair, model fallback, Supabase request or account access. Use non-personal cases. A completed live run returns 0 even if individual generations failed; inspect findings rather than treating exit status as quality evidence.

## What is measured

- Provider return, JSON parsing and strict recipe structural validity are separate stages.
- Constraint passed/failed/unknown counts reuse ConstraintService; ungenerated cases have unevaluated constraints.
- Hard adherence excludes cases with unknown hard checks. Separate check counts retain known conflicts. No allergy-safety certification.
- Ingredient normalization, recognition and USDA match coverage have separate denominators. Quantity normalization does not establish food identity.
- Requested ingredient usage relies on existing canonical identities and state evidence; unresolved evidence stays unknown.
- Nutrition statuses retain verified/partial/unavailable semantics. In fixture mode, verified describes synthetic arithmetic coverage, not real food measurements.
- Repair triggers indicate failed checks; the evaluator neither repairs nor predicts repair success.

Fractions preserve numerator/denominator and null for zero denominators. Provider/schema/timeout failures, constraint failures/uncertainty and coverage issues have distinct finding codes. There is no single quality score or AI judge. Reports omit raw prompts, provider bodies, credentials, account data and exception text.

## Repeatability and limits

Fixture mode uses synthetic providers, no credentials and no external calls. Sorting, case fingerprints and suite/prompt versions are recorded; timestamps vary, while fixture latency is null for reproducibility. Live reports include latency and retain failures individually. Tests include mocked live wiring rather than actual network acceptance.

The suite does not measure taste, cooking feasibility, semantic instruction completeness or broad recipe quality. Source data and curated identity coverage remain limited. Inspect [evaluation documentation](../../docs/evaluation.md) and product limitations before interpreting results.
