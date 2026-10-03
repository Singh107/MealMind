# Evaluation and testing

Offline evaluation measures pipeline regression, not Gemini recipe quality. The 24-case synthetic suite exercises valid generation, restrictions, numeric constraints, missing nutrition, unresolved ingredients, omitted requests and malformed/provider failures. Synthetic food records are not USDA measurements.

From `backend`, run `venv/Scripts/python.exe -m evaluation --mode fixture`. Reports are written under ignored `evaluation/results/`. Metrics preserve denominators and separate provider return, structural validity, coverage and passed/failed/unknown checks. Failed generation has unevaluated constraints, not adherence success. Expected negative cases can meet a regression expectation without being successful recipes.

Live evaluation separately requires `--mode live` and `--acknowledge-live-cost`. CI never runs it. It uses real Gemini/USDA, can incur costs and must not use personal recipe data. Generation is sequential/bounded with no repair or account mutation. The [tooling reference](../backend/evaluation/README.md) documents options and metrics.

Backend tests mock external boundaries and retain selected non-account food/recipe fixtures. Frontend tests cover interaction, account changes, persistence contracts, uncertainty and original preservation. Browser acceptance, food accuracy and deployed RLS enforcement are separate checks; synthetic scores do not replace them.
