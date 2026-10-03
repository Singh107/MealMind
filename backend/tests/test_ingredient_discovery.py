import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4
from app.services.ingredient_catalog import DISCOVERY, IDENTITIES, search_ingredients
from app.services.normalization import IngredientNormalizationService
from app.services.pantry import pantry_identity, PantryService
from app.schemas.pantry import PantryInput
from app.schemas.recipes import RecipeIngredient
from app.core.errors import GenerationError
from app.services.substitution_knowledge import RELATIONSHIPS


def compare(pantry, recipe):
    # Deliberately stale persisted metadata is ignored.
    rows = [dict(id=str(uuid4()), name=n, normalized_name='obsolete', identity_status='unresolved') for n in pantry]
    return PantryService.compare([RecipeIngredient(name=recipe, quantity=1, unit='g')], rows).ingredients[0].status


class DiscoveryTests(unittest.TestCase):
    def test_bundled_catalog_parity_and_unique_ids(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(DISCOVERY, json.loads((root / 'frontend/src/ingredientCatalog.json').read_text()))
        self.assertEqual(len({x['id'] for x in DISCOVERY}), len(DISCOVERY))

    def test_search_alias_and_prefix(self):
        for query, expected in [('rajma','kidney bean'),('kidney','kidney bean'),('garbanzo','chickpea'),
                                ('dahi','yogurt'),('chana','chickpea'),('chicken','chicken')]:
            with self.subTest(query=query): self.assertEqual(search_ingredients(query)[0]['canonical'], expected)

    def test_search_order_and_cleaning(self):
        self.assertEqual([x['canonical'] for x in search_ingredients('chick')][:4],
                         ['chicken','chicken breast','chicken broth','chicken sausage'])
        self.assertEqual(search_ingredients(' RED--KIDNEY beans '), search_ingredients('red kidney beans'))
        self.assertEqual(search_ingredients('chick'), search_ingredients('chick'))
        self.assertEqual(search_ingredients(''), [])

    def test_identity_aliases(self):
        for names, canonical in [(['rajma','kidney beans','red kidney beans'],'kidney bean'),
                                 (['garbanzo beans','chickpeas','chana'],'chickpea'),(['dahi','yogurt'],'yogurt')]:
            for name in names:
                self.assertEqual(IngredientNormalizationService().normalize(name).canonical_name,canonical)
                self.assertEqual(pantry_identity(name)['identity_key'],pantry_identity(canonical)['identity_key'])

    def test_custom_not_a_whitelist(self):
        self.assertEqual(search_ingredients('unknown regional vegetable'), [])
        self.assertEqual(PantryInput(name='unknown regional vegetable').name,'unknown regional vegetable')
        self.assertEqual(pantry_identity('unknown regional vegetable')['identity_status'],'unresolved')

    def test_exact_and_alias_have(self):
        self.assertEqual(compare(['raw chicken breast'],'raw chicken breast'),'available')
        self.assertEqual(compare(['rajma'],'kidney beans'),'available')

    def test_parent_and_states_are_unknown(self):
        for name in ['chicken','raw chicken','cooked chicken breast']:
            with self.subTest(name=name): self.assertEqual(compare([name],'raw chicken breast'),'unknown')
        self.assertEqual(compare(['raw chicken breast'],'chicken'),'unknown')

    def test_dangerous_non_equivalence(self):
        for a,b in [('chicken broth','chicken breast'),('chicken stock','chicken breast'),
                    ('chicken sausage','chicken breast'),('coconut milk','milk'),('peanut oil','peanuts'),
                    ('rice vinegar','rice'),('cream cheese','cheese')]:
            with self.subTest(a=a):
                self.assertNotEqual(pantry_identity(a)['identity_key'],pantry_identity(b)['identity_key'])
                self.assertNotEqual(compare([a],b),'available')

    def test_unrelated_missing(self):
        self.assertEqual(compare(['broccoli'],'raw chicken breast'),'missing')
        self.assertEqual(compare(['chicken broth'],'raw chicken breast'),'missing')

    def test_conflicting_state_unresolved(self):
        self.assertEqual(compare(['raw cooked chicken breast'],'raw chicken breast'),'unknown')
        self.assertEqual(pantry_identity('raw cooked rajma')['identity_status'],'unresolved')

    def test_substitution_relationships_are_context_specific(self):
        self.assertEqual(len(RELATIONSHIPS),140)
        self.assertTrue(all(x.context and x.source_url for x in RELATIONSHIPS))

    def test_composites_discoverable_not_safety_proof(self):
        self.assertTrue(search_ingredients('chicken stock'))
        self.assertIsNone(IngredientNormalizationService().normalize('chicken stock').canonical_name)


class LegacyDuplicateTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_alias_duplicate_no_write(self):
        repository=AsyncMock()
        repository.by_identity.return_value=None
        repository.list.return_value=[dict(id=str(uuid4()),name='rajma',identity_key='legacy')]
        with self.assertRaises(GenerationError) as caught:
            await PantryService(repository).save(PantryInput(name='Kidney beans'))
        self.assertEqual(caught.exception.code,'pantry_duplicate')
        repository.save.assert_not_called()
