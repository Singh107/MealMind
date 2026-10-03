from app.providers.http_limits import bounded_request
from datetime import datetime, timezone
from contextlib import AsyncExitStack
import math
import re
import httpx
from app.core.config import Settings
from app.providers.nutrition import NutritionProviderError
from app.schemas.intelligence import FoodPortion, FoodRecord, NormalizedIngredient, NutrientValues
from app.services.normalization import normalize_unit, parse_quantity

# FDC nutrient IDs, never list positions. Energy alternatives are selected, not summed.
NUTRIENTS = {'calories': ((1008, 2048, 2047), 'kcal'), 'protein': ((1003,), 'g'),
             'carbohydrates': ((1005,), 'g'), 'fat': ((1004, 1085), 'g'),
             'fiber': ((1079,), 'g'), 'sugar': ((2000, 1063), 'g'), 'sodium': ((1093,), 'mg')}


def match_key(name: str) -> tuple[str, ...]:
    words = re.sub(r'[^a-z0-9]+', ' ', name.casefold()).split()
    # These are identity-preserving lexical aliases, not nutrient substitutions.
    text = ' '.join(words)
    # USDA's taxonomic heading adds no species/state information in this exact label.
    if text == 'crustaceans shrimp raw':
        text = 'shrimp raw'
    # Lexical food-part synonyms, never removal of skin/bone/cooking qualifiers.
    text = re.sub(r'\bflorets?\b', 'flower clusters', text)
    text = re.sub(r'\bgarlic cloves?\b', 'garlic', text)
    text = re.sub(r'\bcloves? of garlic\b', 'garlic', text)
    text = re.sub(r'\bbell peppers?\b', 'sweet pepper', text)
    if text.startswith('spices '):
        text = text[len('spices '):]
    if re.search(r'\b(?:pepper|cumin|cinnamon|paprika|turmeric|nutmeg)\b', text) and not re.search(r'\b(?:meat|beef|pork|chicken|turkey)\b', text):
        text = re.sub(r'\bground\b', '', text)
    if 'rice' in text.split():
        text = re.sub(r'\bregular\b', '', text)
        text = re.sub(r'\bdry\b', 'raw', text)
    if text == 'oil olive salad or cooking':
        text = 'olive oil'
    aliases = {'tomatoes': 'tomato', 'lentils': 'lentil', 'chickpeas': 'chickpea',
               'onions': 'onion', 'carrots': 'carrot', 'breasts': 'breast', 'eggs': 'egg',
               'yoghurt': 'yogurt', 'uncooked': 'raw', 'peppers': 'pepper', 'clusters': 'cluster'}
    return tuple(sorted(aliases.get(word, word) for word in text.split()))


def positive_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


class USDAFoodDataCentralProvider:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings, self.transport = settings, transport
        self.client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=self.settings.nutrition_timeout_seconds, transport=self.transport)
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()
        self.client = None

    async def lookup(self, ingredient: NormalizedIngredient) -> FoodRecord | None:
        key = self.settings.usda_api_key.get_secret_value().strip()
        if not key:
            raise NutritionProviderError('USDA nutrition is unavailable because its backend API key is not configured.')
        query = ' '.join(match_key(' '.join(filter(None, [ingredient.name, ingredient.food_state]))))
        try:
            async with AsyncExitStack() as stack:
                client = self.client or await stack.enter_async_context(
                    httpx.AsyncClient(timeout=self.settings.nutrition_timeout_seconds, transport=self.transport))
                # USDA specifies api_key as a query parameter. Do not log URLs/exceptions.
                response = await bounded_request(client, 'POST', 'https://api.nal.usda.gov/fdc/v1/foods/search',
                    params={'api_key': key}, json={'query': query, 'dataType': ['Foundation', 'SR Legacy'], 'pageSize': 100})
                self._check_response(response)
                foods = response.json()['foods']
                if not isinstance(foods, list):
                    raise ValueError('Invalid search list')
                eligible = [food for food in foods if isinstance(food, dict)
                            and food.get('dataType') in ('Foundation', 'SR Legacy')
                            and isinstance(food.get('description'), str)
                            and match_key(food['description']) == match_key(query)
                            and type(food.get('fdcId')) is int]
                # Prefer Foundation when an identical identity/state also exists in
                # SR Legacy. Multiple matches within the preferred dataset abstain.
                legacy = [food for food in eligible if food['dataType'] == 'SR Legacy']
                foundation = [food for food in eligible if food['dataType'] == 'Foundation']
                if foundation:
                    eligible = foundation
                if len(eligible) != 1:
                    return None
                selected = eligible[0]
                details = await bounded_request(client, 'GET', f"https://api.nal.usda.gov/fdc/v1/food/{selected['fdcId']}", params={'api_key': key})
                self._check_response(details)
                body = details.json()
                if (body['fdcId'] != selected['fdcId'] or body['dataType'] != selected['dataType']
                        or match_key(body['description']) != match_key(query)):
                    raise ValueError('Food details do not match search')
                record = self._parse_food(body, ingredient.food_state)
                def usability(food):
                    core = sum(getattr(food.nutrients_per_100g, n) is not None for n in
                               ('calories', 'protein', 'carbohydrates', 'fat'))
                    portion = ingredient.grams is not None or any(p.unit == ingredient.normalized_unit for p in food.portions)
                    return core, portion
                # A single exact SR record may be more usable than an incomplete
                # Foundation record. Never merge foods or broaden food identity.
                if foundation and len(legacy) == 1 and (usability(record)[0] < 4 or not usability(record)[1]):
                    try:
                        alternate = legacy[0]
                        extra = await bounded_request(client, 'GET', f"https://api.nal.usda.gov/fdc/v1/food/{alternate['fdcId']}", params={'api_key': key})
                        if extra.is_success:
                            other = extra.json()
                            if (other.get('fdcId') == alternate['fdcId'] and other.get('dataType') == 'SR Legacy'
                                    and match_key(other.get('description', '')) == match_key(query)):
                                alternative = self._parse_food(other, ingredient.food_state)
                                if usability(alternative) > usability(record):
                                    record = alternative
                    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
                        # Optional refinement must not discard an already valid match.
                        pass
                return record
        except httpx.TimeoutException as exc:
            raise NutritionProviderError('USDA nutrition lookup timed out.') from exc
        except httpx.RequestError as exc:
            raise NutritionProviderError('USDA nutrition service could not be reached.') from exc
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise NutritionProviderError('USDA returned incomplete or malformed food data.') from exc

    @staticmethod
    def _check_response(response: httpx.Response):
        if response.status_code in (401, 403):
            raise NutritionProviderError('USDA rejected its backend credentials.')
        if response.status_code == 429:
            raise NutritionProviderError('USDA request quota is temporarily exhausted.')
        if response.is_error:
            raise NutritionProviderError('USDA nutrition service is unavailable.')

    @staticmethod
    def _parse_food(body: dict, state: str | None) -> FoodRecord:
        values, ids = {}, {}
        rows = body.get('foodNutrients', [])
        for name, (choices, unit) in NUTRIENTS.items():
            values[name] = None
            for nutrient_id in choices:
                matches = [row.get('amount') for row in rows if isinstance(row, dict)
                    and isinstance(row.get('nutrient'), dict) and row['nutrient'].get('id') == nutrient_id
                    and str(row['nutrient'].get('unitName', '')).casefold() == unit]
                if len(matches) == 1 and type(matches[0]) in (int, float) and math.isfinite(matches[0]) and matches[0] >= 0:
                    values[name], ids[name] = matches[0], nutrient_id
                    break
        portions = []
        for portion in body.get('foodPortions', []):
            if not isinstance(portion, dict) or not positive_number(portion.get('gramWeight')):
                continue
            measure = portion.get('measureUnit') or {}
            unit = normalize_unit(measure.get('name')) or normalize_unit(measure.get('abbreviation'))
            label = str(portion.get('modifier') or '').strip()
            description = str(portion.get('portionDescription') or '').strip()
            amount = portion.get('amount')
            if unit:
                # Qualifiers such as packed/chopped/sifted change volume density.
                # Accept only unqualified portions in this first implementation.
                if label and normalize_unit(label) != unit:
                    continue
            else:
                unit = normalize_unit(label)
                if not unit and description:
                    match = re.fullmatch(r'(\d+(?:\.\d+)?|\d+/\d+)\s+(\w+)', description)
                    if match:
                        amount, unit = parse_quantity(match[1]), normalize_unit(match[2])
            if description:
                descriptor = re.fullmatch(r'(\d+(?:\.\d+)?|\d+/\d+)\s+(\w+)', description)
                if not descriptor or normalize_unit(descriptor[2]) != unit or parse_quantity(descriptor[1]) != amount:
                    continue
            if unit and positive_number(amount):
                portions.append(FoodPortion(unit=unit, amount=amount, gram_weight=portion['gramWeight'],
                                            description=description or label or str(measure.get('name'))))
        return FoodRecord(food_id=str(body['fdcId']), description=body['description'], data_type=body['dataType'],
            retrieved_at=datetime.now(timezone.utc).isoformat(), food_state=state,
            nutrients_per_100g=NutrientValues(**values), nutrient_ids=ids, portions=portions)
