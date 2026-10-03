# MealMind API

FastAPI services for recipes, independent nutrition, constraints, repair, Pantry, substitutions and reviewed vision workflows. See the [root README](../README.md) for installation and configuration.

From `backend`, after virtual-environment setup:

```powershell
venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
venv/Scripts/python.exe -m unittest discover -s tests
venv/Scripts/python.exe -m evaluation --mode fixture
```

Development docs are at `/docs`. `/health` checks application reachability, not external providers. Account endpoints require verified Supabase identity. Anonymous generation/photo proposals remain bounded public operations; account persistence is authenticated.

Gemini proposes structured recipes. NutritionService independently normalizes quantities and calculates from matched USDA records. ConstraintService evaluates calculated evidence; missing data stays unknown. Dedicated repair orchestration proposes at most two candidates and reuses these services. See [architecture](../docs/architecture.md).

Configuration belongs in local `.env` or managed environment variables. `.env.example` documents settings; no service-role key is needed. Future production must use `app.main:create_production_app --factory` with explicit production configuration. See [security](../docs/security.md) before deployment.
