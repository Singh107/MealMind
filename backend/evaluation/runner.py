"""Observe the real RecipeService, without replacing its validation/evaluation."""
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
import time
from pydantic import ValidationError
from app.core.errors import GenerationError
from app.schemas.recipes import RecipeCandidate, GeneratedRecipe
from app.services.normalization import IngredientNormalizationService
from app.services.nutrition import NutritionService
from app.services.recipes import RecipeService
from app.services.repair import hard
from app.providers.prompts import PROMPT_VERSION
from .fixtures import EvaluationRecipeProvider, EvaluationNutritionProvider


class ObservedProvider:
    """Retain only stage flags. Never retain provider payloads or exception messages."""
    def __init__(self, provider):
        self.provider = provider
        self.name, self.model = provider.name, provider.model
        self.returned = False
        self.parsed = None
        self.schema = None

    async def generate(self, request):
        raw = await self.provider.generate(request)
        self.returned = True
        try:
            json.loads(raw)
            self.parsed = True
        except (ValueError, TypeError):
            self.parsed = False
        if self.parsed:
            try:
                RecipeCandidate.model_validate_json(raw)
                self.schema = True
            except (ValidationError, ValueError, TypeError):
                self.schema = False
        return raw


def counts(checks):
    return {status: sum(c.status == status for c in checks) for status in ('passed', 'failed', 'unknown')}


def grounding(request, sources):
    normalizer = IngredientNormalizationService()
    requested = [normalizer.normalize(name, 1, 'g') for name in request.selected_ingredients]
    generated = [s.ingredient for s in sources]
    def matches(a, b):
        return bool(a.canonical_name and a.canonical_name == b.canonical_name
                    and a.status != 'unresolved' and b.status != 'unresolved'
                    and (a.food_state is None or a.food_state == b.food_state))
    used = sum(any(matches(a, b) for b in generated) for a in requested)
    unknown = sum(a.canonical_name is None or a.status == 'unresolved' for a in requested)
    # A recognized but ambiguous generated identity cannot establish omission.
    omitted = sum(a.canonical_name is not None and not any(matches(a, b) for b in generated)
                  and not any(b.canonical_name is None or b.status == 'unresolved' for b in generated)
                  for a in requested)
    return dict(requested_entries=len(requested), used=used, omitted=omitted,
        unknown=len(requested)-used-omitted,
        additional=sum(b.canonical_name is not None and not any(matches(a, b) for a in requested)
                       for b in generated) if not unknown else None,
        generated_entries=len(generated), recognized=sum(b.canonical_name is not None and b.status != 'unresolved' for b in generated),
        normalized=sum(b.status == 'normalized' for b in generated),
        unresolved=sum(b.canonical_name is None or b.status == 'unresolved' for b in generated),
        conflicting_states=sum(b.reason == 'Conflicting food preparation states.' for b in generated))


async def evaluate_case(case, provider, nutrition, *, mode='fixture', timeout=45):
    observer = ObservedProvider(provider)
    started = time.monotonic()
    result = dict(case_id=case.id, tags=case.tags, mode=mode, provider=observer.name,
        model=observer.model, generation_status='failed', structural_validity=False,
        provider_returned=False, json_parse_success=None, candidate_schema_valid=None,
        identifiers_valid=None, latency_seconds=None, constraints=None, hard_constraints=None,
        nonhard_constraints=None, hard_failures=[], unknown_checks=[], grounding=None,
        nutrition=None, repairability=None, findings=[], expectation_pass=None)
    findings = result['findings']
    try:
        async with asyncio.timeout(timeout):
            response = await RecipeService(observer, timeout, nutrition).generate(case.request, 'evaluation')
        GeneratedRecipe.model_validate(response.recipe)
        result.update(generation_status='succeeded', structural_validity=True,
                      identifiers_valid=bool(response.recipe.id != response.recipe.recipe_version_id))
        checks = response.constraint_results
        hard_checks = [c for c in checks if hard(c)]
        result.update(constraints=counts(checks), hard_constraints=counts(hard_checks),
                      nonhard_constraints=counts([c for c in checks if not hard(c)]),
                      hard_failures=[c.constraint for c in hard_checks if c.status == 'failed'],
                      unknown_checks=[c.constraint for c in checks if c.status == 'unknown'])
        if result['hard_failures']:
            findings.append('HARD_CONSTRAINT_FAILURE')
        if result['nonhard_constraints']['failed']:
            findings.append('NUMERIC_CONSTRAINT_FAILURE')
        if result['unknown_checks']:
            findings.append('CONSTRAINT_UNKNOWN')
        result['repairability'] = dict(
            all_requested_passed=bool(checks) and all(c.status == 'passed' for c in checks),
            no_requested_constraints=not checks,
            repair_trigger=any(c.status == 'failed' for c in checks),
            hard_conflict=bool(result['hard_failures']),
            unknown=bool(result['unknown_checks']))
        result['grounding'] = grounding(case.request, response.nutrition_sources)
        for field, finding in [('unresolved', 'UNRESOLVED_INGREDIENT'),
                               ('conflicting_states', 'CONFLICTING_INGREDIENT_STATE'),
                               ('omitted', 'REQUESTED_INGREDIENT_OMITTED')]:
            if result['grounding'][field]:
                findings.append(finding)
        sources = response.nutrition_sources
        result['nutrition'] = dict(status=response.nutrition_status, ingredient_entries=len(sources),
            matched=sum(s.food is not None for s in sources),
            calculated=sum(s.status == 'calculated' for s in sources),
            unavailable=sum(s.status == 'unavailable' for s in sources),
            nutrient_coverage=response.calculated_nutrition.coverage)
        if response.nutrition_status != 'verified':
            findings.append('NUTRITION_' + response.nutrition_status.upper())
        if result['nutrition']['unavailable']:
            findings.append('NUTRITION_PROVIDER_UNAVAILABLE')
        if mode == 'fixture':
            result['expectation_pass'] = all(any(c.constraint == e.constraint and c.requested == e.requested
                and c.status == e.status for c in checks) for e in case.expected_constraints)
    except (GenerationError, TimeoutError) as exc:
        code = exc.code if isinstance(exc, GenerationError) else 'provider_timeout'
        if code == 'provider_timeout':
            findings.append('TIMEOUT')
        elif observer.parsed is False:
            findings.append('PARSE_ERROR')
        elif observer.schema is False or code == 'invalid_provider_output':
            findings.append('SCHEMA_ERROR' if observer.schema is False else 'INVALID_PROVIDER_OUTPUT')
        else:
            findings.append('PROVIDER_ERROR')
    except Exception:
        findings.append('INTERNAL_EVALUATION_ERROR')
    result.update(provider_returned=observer.returned, json_parse_success=observer.parsed,
                  candidate_schema_valid=observer.schema)
    if mode == 'live':
        result['latency_seconds'] = round(time.monotonic() - started, 4)
    result['findings'] = sorted(set(findings))
    if mode == 'fixture':
        result['expectation_pass'] = (result['expectation_pass'] is not False
            and result['structural_validity'] == (case.expected_structure == 'valid')
            and set(case.expected_findings).issubset(findings)
            and 'INTERNAL_EVALUATION_ERROR' not in findings)
    return result


def ratio(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                rate=round(numerator / denominator, 6) if denominator else None)


def aggregate(results):
    evaluated = [r for r in results if r['constraints'] is not None]
    checks = {key: sum(r['constraints'][key] for r in evaluated) for key in ('passed', 'failed', 'unknown')}
    hard_counts = {key: sum(r['hard_constraints'][key] for r in evaluated) for key in checks}
    # Case-level verifiability: any unknown makes that entire hard-restriction case unknown.
    hard_cases = Counter()
    for r in evaluated:
        c = r['hard_constraints']
        state = 'not_requested' if not sum(c.values()) else 'unknown' if c['unknown'] else 'failed' if c['failed'] else 'passed'
        hard_cases[state] += 1
    grounding_rows = [r['grounding'] for r in evaluated]
    return dict(total_cases=len(results), evaluated_constraints_cases=len(evaluated),
        provider_return_rate=ratio(sum(r['provider_returned'] for r in results), len(results)),
        generation_success_rate=ratio(sum(r['generation_status'] == 'succeeded' for r in results), len(results)),
        structural_validity_rate=ratio(sum(r['structural_validity'] for r in results), len(results)),
        constraint_counts=checks, hard_check_counts=hard_counts, hard_case_counts=dict(sorted(hard_cases.items())),
        hard_adherence_verifiable_cases=ratio(hard_cases['passed'], hard_cases['passed'] + hard_cases['failed']),
        nutrition_counts=dict(sorted(Counter(r['nutrition']['status'] for r in evaluated).items())),
        recognized_ingredient_coverage=ratio(sum(g['recognized'] for g in grounding_rows), sum(g['generated_entries'] for g in grounding_rows)),
        normalized_ingredient_coverage=ratio(sum(g['normalized'] for g in grounding_rows), sum(g['generated_entries'] for g in grounding_rows)),
        requested_usage=ratio(sum(g['used'] for g in grounding_rows), sum(g['requested_entries'] for g in grounding_rows)),
        nutrition_match_coverage=ratio(sum(r['nutrition']['matched'] for r in evaluated), sum(r['nutrition']['ingredient_entries'] for r in evaluated)),
        finding_counts=dict(sorted(Counter(f for r in results for f in r['findings']).items())),
        regression_expectations=ratio(sum(r['expectation_pass'] is True for r in results),
                                     sum(r['expectation_pass'] is not None for r in results)))


async def run(cases, mode='fixture'):
    if mode not in ('fixture', 'live') or not 1 <= len(cases) <= 25:
        raise ValueError('Mode must be fixture/live; case count must be 1-25.')
    if len({c.id for c in cases}) != len(cases):
        raise ValueError('Duplicate case IDs')
    results = []
    settings = None
    if mode == 'live':
        from app.core.config import get_settings
        settings = get_settings()
    for case in sorted(cases, key=lambda c: c.id):
        if mode == 'fixture':
            result = await evaluate_case(case, EvaluationRecipeProvider(case),
                NutritionService(EvaluationNutritionProvider(case.fixture)))
        else:
            from app.providers.gemini import GeminiRecipeProvider
            from app.providers.usda import USDAFoodDataCentralProvider
            from app.services.nutrition_cache import CachedNutritionProvider, InMemoryFoodCache
            async with USDAFoodDataCentralProvider(settings) as provider:
                nutrition = NutritionService(CachedNutritionProvider(provider,
                    InMemoryFoodCache(settings.nutrition_cache_ttl_seconds, settings.nutrition_cache_max_entries)), settings.nutrition_timeout_seconds)
                result = await evaluate_case(case, GeminiRecipeProvider(settings), nutrition,
                    mode='live', timeout=settings.generation_timeout_seconds)
        results.append(result)
    case_fingerprint = hashlib.sha256(json.dumps([c.model_dump(mode='json') for c in
        sorted(cases, key=lambda c: c.id)], sort_keys=True).encode()).hexdigest()
    return dict(report_version='1', suite_version='synthetic-v1', case_fingerprint=case_fingerprint,
        prompt_version=PROMPT_VERSION, timestamp=datetime.now(timezone.utc).isoformat(),
        label='PIPELINE REGRESSION BASELINE' if mode == 'fixture' else 'LIVE MODEL EVALUATION',
        mode=mode, repeat_count=1, concurrency=1, results=results, aggregate=aggregate(results),
        limitations=[
            'Fixture results measure pipeline regression, not Gemini quality. Synthetic nutrients are not USDA measurements.',
            'UNKNOWN is never PASS. Failed generation has unevaluated constraints, not zero failures or adherence.',
            'Hard case adherence excludes any unknown check; hard check counts separately retain conflicts.',
            'Grounding uses existing canonical identities and state evidence; unresolved evidence remains unknown.',
            'Requested usage counts request entries; prompt requires their use but permits necessary additions.',
            'Cooking time is model-proposed metadata, not measured cooking performance. No medical allergy-safety claim.',
            'Repair trigger follows existing failed-check behavior; no repair is invoked or success predicted.',
            'Fixture latency is null for reproducible results. Timestamp alone changes between fixture reports.',
            'Live calls retain existing provider retry policy (at most two HTTP attempts per generation); no evaluator retries.'])


def markdown(report):
    lines = ['# ' + report['label'], '', 'Timestamp: ' + report['timestamp'],
             'Mode: ' + report['mode'],
             'Provider/model: ' + ', '.join(sorted({r['provider'] + '/' + r['model'] for r in report['results']})),
             'Prompt: ' + report['prompt_version'] + '; suite: ' + report['suite_version'],
             '', '## Aggregate metrics', '', '```json',
             json.dumps(report['aggregate'], indent=2, sort_keys=True), '```', '',
             '## Cases', '', '| Case | Generation | Nutrition | Findings | Regression expectation |',
             '| --- | --- | --- | --- | --- |']
    for r in report['results']:
        lines.append(f"| {r['case_id']} | {r['generation_status']} | {(r['nutrition'] or {}).get('status', 'not evaluated')} | {', '.join(r['findings']) or 'none'} | {r['expectation_pass']} |")
    lines += ['', '## Limits', ''] + ['- ' + item for item in report['limitations']]
    return '\n'.join(lines) + '\n'
