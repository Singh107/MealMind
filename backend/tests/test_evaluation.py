import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from evaluation.cases import EvaluationCase, ExpectedCheck, load_cases
from evaluation.fixtures import EvaluationNutritionProvider, EvaluationRecipeProvider
from evaluation.runner import evaluate_case, run, aggregate, markdown
from evaluation.__main__ import main
from app.services.nutrition import NutritionService


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cases = load_cases()
        self.report = await run(self.cases)
        self.rows = {r['case_id']: r for r in self.report['results']}

    def test_case_schema(self):
        self.assertEqual(len(self.cases), 24)
        data = self.cases[0].model_dump()
        data['request']['user_id'] = 'forged'
        with self.assertRaises(ValidationError):
            EvaluationCase.model_validate(data)

    def test_restriction_expectations_preserved(self):
        data = self.cases[0].model_dump()
        data['expected_hard_restrictions'] = {}
        with self.assertRaises(ValidationError):
            EvaluationCase.model_validate(data)

    async def test_repeatable_fixture_and_order(self):
        other = await run(list(reversed(self.cases)))
        for report in (other, self.report):
            report.pop('timestamp')
        self.assertEqual(other, self.report)
        self.assertTrue(all(r['expectation_pass'] for r in other['results']))

    def test_structural_metrics(self):
        self.assertEqual(self.report['aggregate']['structural_validity_rate']['numerator'], 20)
        self.assertTrue(self.rows['ordinary']['identifiers_valid'])
        self.assertTrue(self.rows['ordinary']['candidate_schema_valid'])

    def test_pass_fail_unknown(self):
        counts = self.report['aggregate']['constraint_counts']
        self.assertTrue(all(counts[s] > 0 for s in ('passed', 'failed', 'unknown')))
        self.assertEqual(self.rows['nutrition-unavailable']['constraints']['unknown'], 1)

    def test_hard_failure(self):
        r = self.rows['hard-conflict']
        self.assertIn('HARD_CONSTRAINT_FAILURE', r['findings'])
        self.assertTrue(r['repairability']['hard_conflict'])
        self.assertTrue(r['repairability']['repair_trigger'])

    def test_provider_error(self):
        r = self.rows['provider-outage']
        self.assertEqual(r['findings'], ['PROVIDER_ERROR'])
        self.assertIsNone(r['constraints'])
        self.assertFalse(r['provider_returned'])

    def test_timeout(self):
        self.assertEqual(self.rows['provider-timeout']['findings'], ['TIMEOUT'])

    async def test_actual_deadline_cancellation(self):
        class Slow:
            name, model = 'test', 'test'
            async def generate(self, request):
                await asyncio.sleep(10)
        result = await evaluate_case(self.cases[0], Slow(),
            NutritionService(EvaluationNutritionProvider('normal')), timeout=.01)
        self.assertEqual(result['findings'], ['TIMEOUT'])

    def test_parse_schema_distinct(self):
        self.assertFalse(self.rows['invalid-json']['json_parse_success'])
        self.assertIsNone(self.rows['invalid-json']['candidate_schema_valid'])
        self.assertTrue(self.rows['invalid-schema']['json_parse_success'])
        self.assertFalse(self.rows['invalid-schema']['candidate_schema_valid'])

    def test_nutrition_states(self):
        for case, state in [('ordinary', 'verified'), ('unusual-valid', 'partial'), ('nutrition-unavailable', 'unavailable')]:
            self.assertEqual(self.rows[case]['nutrition']['status'], state)

    def test_denominators(self):
        a = self.report['aggregate']
        self.assertEqual(a['structural_validity_rate']['denominator'], 24)
        self.assertEqual(a['evaluated_constraints_cases'], 20)
        a = aggregate([self.rows['allergy-uncertain'], self.rows['provider-outage']])
        self.assertEqual(a['hard_adherence_verifiable_cases'], {'numerator': 0, 'denominator': 0, 'rate': None})
        self.assertEqual(a['hard_case_counts'], {'unknown': 1})

    def test_grounding(self):
        self.assertEqual(self.rows['ordinary']['grounding']['used'], 2)
        self.assertEqual(self.rows['omitted-request']['grounding']['omitted'], 1)
        self.assertEqual(self.rows['hard-conflict']['grounding']['additional'], 1)
        self.assertEqual(self.rows['conflicting-state']['grounding']['conflicting_states'], 1)

    def test_json_and_markdown(self):
        self.assertEqual(json.loads(json.dumps(self.report)), self.report)
        summary = markdown(self.report)
        self.assertIn('PIPELINE REGRESSION BASELINE', summary)
        self.assertIn('UNKNOWN is never PASS', summary)
        self.assertIn('provider-outage', summary)

    async def test_no_exception_secret_leakage(self):
        class Broken:
            name, model = 'test', 'test'
            async def generate(self, request):
                raise RuntimeError('PRIVATE_SENTINEL_PASSWORD')
        row = await evaluate_case(self.cases[0], Broken(), NutritionService(EvaluationNutritionProvider('normal')))
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(row))
        self.assertEqual(row['findings'], ['INTERNAL_EVALUATION_ERROR'])
        self.assertFalse(row['expectation_pass'])

    async def test_offline_has_no_network_or_settings(self):
        with patch('app.core.config.get_settings', side_effect=AssertionError('settings used')), \
             patch('httpx.AsyncClient.send', side_effect=AssertionError('network used')):
            result = await run(self.cases)
        self.assertTrue(all(r['expectation_pass'] for r in result['results']))

    async def test_expected_constraint_mismatch(self):
        case = next(c for c in self.cases if c.id == 'calorie-maximum').model_copy(deep=True)
        case.expected_constraints = [ExpectedCheck(constraint='maximum_calories', requested=20., status='passed')]
        report = await run([case])
        self.assertFalse(report['results'][0]['expectation_pass'])

    async def test_invalid_mode_and_case_count(self):
        for cases, mode in [(self.cases, 'auto'), ([], 'fixture'), (self.cases * 2, 'fixture')]:
            with self.assertRaises(ValueError):
                await run(cases, mode)

    async def test_live_wiring_with_mocked_transports(self):
        from app.core.config import Settings
        case = next(c for c in self.cases if c.id == 'ordinary')
        provider = EvaluationRecipeProvider(case)
        provider.name, provider.model = 'gemini', 'configured-test-model'
        class Food(EvaluationNutritionProvider):
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
        settings = Settings(gemini_model='configured-test-model')
        with patch('app.core.config.get_settings', return_value=settings), \
             patch('app.providers.gemini.GeminiRecipeProvider', return_value=provider) as factory, \
             patch('app.providers.usda.USDAFoodDataCentralProvider', return_value=Food('normal')), \
             patch('httpx.AsyncClient.send', side_effect=AssertionError('Network forbidden')):
            report = await run([case], 'live')
        factory.assert_called_once_with(settings)
        row = report['results'][0]
        self.assertEqual(row['model'], 'configured-test-model')
        self.assertEqual(row['generation_status'], 'succeeded')
        self.assertIsNone(row['expectation_pass'])
        self.assertGreaterEqual(row['latency_seconds'], 0)


class EvaluationCLITests(unittest.TestCase):
    def test_live_requires_acknowledgement(self):
        with patch('evaluation.__main__.run') as runner:
            with self.assertRaises(SystemExit):
                main(['--mode', 'live', '--limit', '1'])
            runner.assert_not_called()

    def test_fixture_default_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report'
            self.assertEqual(main(['--case', 'ordinary', '--output', str(path)]), 0)
            self.assertEqual(json.loads(path.with_suffix('.json').read_text())['mode'], 'fixture')
            self.assertTrue(path.with_suffix('.md').exists())

    def test_bounds_and_unknown_cases(self):
        for args in [['--limit', '26'], ['--limit', '0'], ['--case', 'unknown']]:
            with self.assertRaises(SystemExit):
                main(args)
