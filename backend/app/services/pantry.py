"""Pantry orchestration reuses normalization, never USDA or an LLM.

The nutrition catalog contains composition categories, not universal substitutes
(e.g. peanut/peanut butter). Only exact names, curated discovery aliases and
catalog-backed plurals share a pantry identity. Explicit parent relations yield
uncertainty only. Unknown/qualified names remain unresolved for coverage.
"""
import hashlib
import json
import re
from app.core.errors import GenerationError
from app.schemas.pantry import PantryInput, PantryItem, PantryCompatibility, IngredientAvailability
from app.services.normalization import IngredientNormalizationService, normalize_unit, MASS_GRAMS, parse_quantity
from app.services.ingredient_catalog import clean_name, DISCOVERY_ALIASES, related_identity


def pantry_identity(name: str) -> dict:
    normalized = IngredientNormalizationService().normalize(name)
    base = clean_name(normalized.name)
    canonical = normalized.canonical_name
    discovery = DISCOVERY_ALIASES.get(base)
    if canonical and discovery:
        # Only the curated name aliases, never composition-only aliases such as peanut butter.
        base = discovery['canonical']
    # Only conservative plural variants of an already recognized catalog entry.
    if canonical and (base == canonical or base == canonical + 's' or
                      base == canonical + 'es' or
                      (base.endswith('ies') and base[:-3] + 'y' == canonical)):
        base = canonical
    conflict = normalized.reason == 'Conflicting food preparation states.'
    # Quantity-free normalization reports missing quantity first. Detect state
    # conflicts using a second normalization with an explicit neutral mass basis.
    state_check = IngredientNormalizationService().normalize(name, 1, 'g')
    conflict = conflict or state_check.reason == 'Conflicting food preparation states.'
    if conflict:
        base = clean_name(name)
    if not base:
        # Do not collapse non-Latin/unrecognized names to the same empty identity.
        base = ' '.join(name.casefold().split())
    key = hashlib.sha256(json.dumps([base, normalized.food_state, conflict], ensure_ascii=False).encode()).hexdigest()
    return {'normalized_name': base, 'food_state': normalized.food_state,
            'identity_status': 'recognized' if canonical and not conflict else 'unresolved',
            'identity_key': key}


class PantryService:
    def __init__(self, repository):
        self.repository = repository

    @staticmethod
    def public(row):
        return PantryItem.model_validate({k: row[k] for k in PantryItem.model_fields})

    async def list(self):
        return [self.public(row) for row in await self.repository.list()]

    async def get(self, item_id):
        return self.public(await self.repository.get(item_id))

    async def save(self, body: PantryInput, item_id=None):
        if item_id is not None:
            await self.repository.get(item_id)
        values = {**body.model_dump(), **pantry_identity(body.name)}
        existing = await self.repository.by_identity(values['identity_key'])
        if existing and str(existing['id']) != str(item_id):
            raise GenerationError('pantry_duplicate', 'This ingredient is already in your pantry. Edit the existing item instead.', 409, False)
        # Legacy rows can retain pre-catalog keys. Compare names without rewriting stored data.
        if any(str(row['id']) != str(item_id) and pantry_identity(row['name'])['identity_key'] == values['identity_key']
               for row in await self.repository.list()):
            raise GenerationError('pantry_duplicate', 'This ingredient is already in your pantry. Edit the existing item instead.', 409, False)
        row = await self.repository.save(values, item_id)
        return self.public(row)

    async def compatibility(self, ingredients):
        return self.compare(ingredients, await self.repository.list())

    @staticmethod
    def compare(ingredients, pantry):
        # Recompute from names; stored/client-normalized metadata is not authority.
        identities = [(row, presence_identity(row['name'])) for row in pantry]
        results = []
        for index, ingredient in enumerate(ingredients):
            identity = presence_identity(ingredient.name)
            quantity_status, quantity_reason = 'unknown', 'Check quantity; amounts are not safely comparable.'
            status, reason, item_id = 'unknown', 'Ingredient identity is unresolved; check manually.', None
            if identity['identity_status'] == 'recognized':
                matches = [(row, value) for row, value in identities
                           if value['identity_status'] == 'recognized' and value['normalized_name'] == identity['normalized_name']
                           and (value['food_state'] == identity['food_state'] or
                                (identity['normalized_name'] in ('chicken breast', 'chicken thigh') and {value['food_state'], identity['food_state']} <= {None, 'raw'}))]
                if matches:
                    row, matched = matches[0]
                    status, reason, item_id = 'available', 'Ingredient present; check preparation and the separate quantity result.', row['id']
                    # Repeated recipe rows cannot each claim the same stock is enough.
                    repeated = sum(presence_identity(x.name)['normalized_name'] == identity['normalized_name'] for x in ingredients) > 1
                    if not repeated and matched['food_state'] == identity['food_state'] and clean_name(row['name']) == clean_name(ingredient.name):
                        quantity_status, quantity_reason = quantity_fit(row, ingredient)
                    elif not repeated and pantry_identity(row['name'])['identity_key'] == pantry_identity(ingredient.name)['identity_key']:
                        quantity_status, quantity_reason = quantity_fit(row, ingredient)
                elif any(value['normalized_name'] == identity['normalized_name'] or
                         related_identity(value['normalized_name'], identity['normalized_name']) or
                         (value['identity_status'] == 'unresolved' and
                          re.search(r'\b' + re.escape(identity['normalized_name']) + r'\b', value['normalized_name']))
                         for _, value in identities):
                    reason = 'Related pantry name has uncertain identity or food state; check manually.'
                else:
                    status, reason = 'missing', 'No matching recognized ingredient in this pantry.'
            results.append(IngredientAvailability(ingredient_index=index, name=ingredient.name,
                           status=status, reason=reason, pantry_item_id=item_id,
                           quantity_status=quantity_status, quantity_reason=quantity_reason))
        available = sum(r.status == 'available' for r in results)
        usable = sum(value['identity_status'] == 'recognized' for _, value in identities)
        return PantryCompatibility(pantry_count=len(pantry), usable_pantry_count=usable, ingredient_count=len(results), available_count=available,
            missing_count=sum(r.status == 'missing' for r in results), unknown_count=sum(r.status == 'unknown' for r in results),
            coverage_percent=round(100 * available / len(results), 1) if usable else None, ingredients=results)


def presence_identity(name):
    """Possession only: qualifiers stay intact for storage, nutrition and safety."""
    simple = re.sub(r'\b(?:boneless|skinless)\b', '', name, flags=re.I)
    simple = ' '.join(simple.split())
    # Only explicitly curated poultry cuts; no parent-to-child equivalence.
    candidate = pantry_identity(simple)
    if candidate['normalized_name'] in ('chicken breast', 'chicken thigh'):
        return candidate
    # Canned drained beans are present as canned beans, but not equal weights.
    simple = re.sub(r'[, ]+drained solids\b', '', IngredientNormalizationService().normalize(name).name)
    original = pantry_identity(name)
    if original['food_state'] == 'canned' and simple in ('black beans', 'kidney beans', 'chickpeas'):
        return pantry_identity('canned ' + simple)
    return original


def quantity_fit(row, ingredient):
    amount, required = parse_quantity(row.get('quantity')), ingredient.quantity
    left, right = normalize_unit(row.get('unit')), normalize_unit(ingredient.unit)
    if amount is None or not left or not right:
        return 'unknown', 'Check quantity; an amount or unit is missing.'
    if left in MASS_GRAMS and right in MASS_GRAMS:
        enough = amount * MASS_GRAMS[left] >= required * MASS_GRAMS[right]
    elif left in ('ml', 'l') and right in ('ml', 'l'):
        enough = amount * (1000 if left == 'l' else 1) >= required * (1000 if right == 'l' else 1)
    elif left == right and left in ('cup', 'tbsp', 'tsp', 'piece', 'clove', 'breast', 'egg', 'slice'):
        enough = amount >= required
    else:
        return 'unknown', 'Check quantity; no trusted conversion between these units.'
    return ('sufficient' if enough else 'insufficient'), 'Compared stated amounts for the same ingredient and form; no portion weight assumed.'
