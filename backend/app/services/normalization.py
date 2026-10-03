import math
import re
from fractions import Fraction
from app.schemas.intelligence import NormalizedIngredient
from app.services.ingredient_catalog import identity_for

UNIT_ALIASES = {
    'g': 'g', 'gram': 'g', 'grams': 'g', 'kg': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
    'mg': 'mg', 'milligram': 'mg', 'milligrams': 'mg',
    'oz': 'oz', 'ounce': 'oz', 'ounces': 'oz', 'lb': 'lb', 'lbs': 'lb', 'pound': 'lb', 'pounds': 'lb',
    'ml': 'ml', 'milliliter': 'ml', 'milliliters': 'ml', 'l': 'l', 'liter': 'l', 'liters': 'l',
    'tsp': 'tsp', 'teaspoon': 'tsp', 'teaspoons': 'tsp',
    'tbsp': 'tbsp', 'tablespoon': 'tbsp', 'tablespoons': 'tbsp', 'cup': 'cup', 'cups': 'cup',
    'piece': 'piece', 'pieces': 'piece', 'count': 'piece', 'whole': 'piece', 'clove': 'clove', 'cloves': 'clove',
    'breast': 'breast', 'breasts': 'breast', 'egg': 'egg', 'eggs': 'egg', 'slice': 'slice', 'slices': 'slice',
    'large': 'large', 'medium': 'medium', 'small': 'small',
}
MASS_GRAMS = {'g': 1, 'kg': 1000, 'mg': .001, 'oz': 28.349523125, 'lb': 453.59237}
STATES = ('raw', 'uncooked', 'dry', 'dried', 'cooked', 'boiled', 'roasted', 'fried', 'steamed', 'baked', 'canned')
PREPARATION = ('chopped', 'diced', 'sliced', 'minced', 'grated', 'peeled', 'crushed', 'rinsed')


def normalize_unit(unit: str | None) -> str | None:
    return UNIT_ALIASES.get((unit or '').strip().casefold().rstrip('.'))


def parse_quantity(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        raw = str(value).strip().lower()
        raw = re.sub(r'(\d)([½¼¾⅓⅔])', r'\1 \2', raw)
        for source, target in {'½': '1/2', '¼': '1/4', '¾': '3/4', '⅓': '1/3', '⅔': '2/3', 'half': '1/2', 'quarter': '1/4'}.items():
            raw = raw.replace(source, target)
        parts = raw.split()
        if len(parts) > 2 or (len(parts) == 2 and ('/' not in parts[1] or '/' in parts[0])):
            return None
        number = float(sum(Fraction(part) for part in parts))
        return number if math.isfinite(number) and 0 < number <= 100000 else None
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


class IngredientNormalizationService:
    def normalize(self, name: str, quantity=None, unit: str | None = None) -> NormalizedIngredient:
        original = f'{quantity} {unit} {name}' if quantity is not None else name
        name = name.strip()
        if quantity is None and unit is None:
            match = re.match(r'^(\d+\s+\d+/\d+|\d+[½¼¾⅓⅔]|\d+/\d+|\d*\.\d+|\d+|[½¼¾⅓⅔]|half|quarter)\s+(?:(?:a|an|of a)\s+)?(.+)$', name, re.I)
            if match:
                quantity, rest = match.groups()
                first, _, tail = rest.partition(' ')
                if normalize_unit(first) or first.casefold() in ('pinch', 'pinches', 'handful', 'handfuls', 'bunch', 'bunches', 'can', 'cans', 'package', 'packages'):
                    unit, name = first, re.sub(r'^of\s+', '', tail)
                else:
                    # Counts with no size are kept, but require a matching food portion.
                    unit, name = 'piece', rest
        name = re.sub(r'\bcut into florets\b', 'florets', name, flags=re.I)
        # Remove only a complete recognized preparation suffix. Keep drained
        # solids as a nutritional distinction, and never strip arbitrary "and".
        name = re.sub(r',\s*peeled and deveined\s*$', ', peeled', name, flags=re.I)
        name = re.sub(r',\s*rinsed and drained\s*$', ', drained solids, rinsed', name, flags=re.I)
        amount = parse_quantity(quantity)
        normalized_unit = normalize_unit(unit)
        cut = re.search(r',\s*(cut into (?:bite-sized |small |large )?(?:pieces|cubes|strips)|freshly cracked)\s*$', name, re.I)
        cutting = cut.group(1) if cut else None
        if cut:
            name = name[:cut.start()]
        name = re.sub(r'\b(?:finely|roughly|thinly|coarsely|freshly)\s+(?=' + '|'.join(PREPARATION) + r'\b)', '', name, flags=re.I)
        state_words = re.findall(r'\b(' + '|'.join(STATES) + r')\b', name.casefold())
        state_words = ['raw' if state == 'uncooked' else state for state in state_words]
        prep_words = re.findall(r'\b(' + '|'.join(PREPARATION) + r')\b', name.casefold())
        if cutting:
            prep_words.append(cutting)
        food_state = state_words[0] if len(set(state_words)) == 1 else None
        if food_state == 'uncooked':
            food_state = 'raw'
        base = re.sub(r'\b(' + '|'.join(STATES + PREPARATION) + r')\b', '', name, flags=re.I)
        base = re.sub(r'\s*,\s*,\s*', ', ', base)
        base = ' '.join(base.strip(' ,').split())
        if re.fullmatch(r'fresh (lime|lemon) juice', base, re.I) and food_state in (None, 'raw'):
            base, food_state = base[6:], 'raw'
        # Explicit fresh garlic/onion/broccoli denotes the uncooked ingredient.
        # Preserve fresh/dried distinctions for all other foods and herbs.
        plain = ' '.join(base.replace(',', ' ').split())
        without_fresh = ' '.join(word for word in plain.split() if word.casefold() != 'fresh')
        if food_state in (None, 'raw') and without_fresh != plain and re.fullmatch(
                r'(?:garlic(?: cloves?)?|onions?|broccoli(?: florets?)?)', without_fresh, re.I):
            base, food_state = without_fresh, 'raw'
        identity = identity_for(base)
        reason = None
        status = 'normalized'
        grams = None
        evidence = None
        if amount is None or not base:
            status, reason = 'unresolved', 'Missing or unsupported positive quantity/name.'
        elif normalized_unit is None:
            status, reason = 'unresolved', 'Unsupported measurement unit; enter a gram weight.'
        elif len(set(state_words)) > 1:
            status, reason = 'unresolved', 'Conflicting food preparation states.'
        elif normalized_unit in MASS_GRAMS:
            grams = amount * MASS_GRAMS[normalized_unit]
            evidence = f'Mass unit conversion: 1 {normalized_unit} = {MASS_GRAMS[normalized_unit]} g; edible ingredient weight.'
        else:
            status, reason = 'needs_conversion', 'A matching USDA portion weight is required; volume/count is not assumed to equal grams.'
        return NormalizedIngredient(original_text=original, name=base or name,
            canonical_name=identity.name if identity else None, quantity=amount, unit=unit,
            normalized_unit=normalized_unit, preparation=', '.join(prep_words) or None,
            food_state=food_state, grams=grams, status=status, reason=reason, conversion_evidence=evidence)
