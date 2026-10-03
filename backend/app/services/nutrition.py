import asyncio
from decimal import Decimal
from app.providers.nutrition import NutritionProvider, NutritionProviderError
from app.schemas.intelligence import (CalculatedNutrition, IngredientNutrition, NormalizedIngredient,
                                      NutrientValues, RecipeIntelligence)

NAMES = tuple(NutrientValues.model_fields)
CORE = ('calories', 'protein', 'carbohydrates', 'fat')
# US nutrition-label household measures (21 CFR 101.9(b)(5)(viii)).
# These convert volume to volume; mass still comes from the matched USDA record.
VOLUME_ML = {'ml': Decimal(1), 'l': Decimal(1000), 'tsp': Decimal(5),
             'tbsp': Decimal(15), 'cup': Decimal(240)}


class NutritionService:
    def __init__(self, provider: NutritionProvider, timeout_seconds: float = 10):
        self.provider, self.timeout_seconds = provider, timeout_seconds

    async def calculate(self, ingredients: list[NormalizedIngredient], servings: int,
                        remaining_seconds: float | None = None) -> RecipeIntelligence:
        if servings <= 0:
            raise ValueError('Servings must be positive')
        results = []
        looked_up = {}
        budget = self.timeout_seconds if remaining_seconds is None else min(self.timeout_seconds, remaining_seconds)
        semaphore = asyncio.Semaphore(4)
        stopped = False

        async def lookup(key, ingredient):
            nonlocal stopped
            async with semaphore:
                if stopped:
                    return
                try:
                    looked_up[key] = await self.provider.lookup(ingredient)
                except (NutritionProviderError, TimeoutError):
                    stopped = True

        unique = {(item.name.casefold(), item.food_state): item for item in ingredients if item.status != 'unresolved'}
        tasks = [asyncio.create_task(lookup(key, item)) for key, item in unique.items()] if budget > 0 else []
        try:
            if tasks:
                _, pending = await asyncio.wait(tasks, timeout=max(0, budget))
                for task in pending:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=False)
        except asyncio.CancelledError:
            # Deadline cancellation preserves successful siblings. Parent request
            # cancellation still cancels every child and propagates below.
            if asyncio.current_task().cancelling():
                raise
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        for index, original in enumerate(ingredients):
            ingredient = original.model_copy(deep=True)
            result = IngredientNutrition(ingredient_index=index, ingredient=ingredient, status='unavailable')
            results.append(result)
            if ingredient.status == 'unresolved':
                result.status, result.reason = 'unconvertible', ingredient.reason
                continue
            key = (ingredient.name.casefold(), ingredient.food_state)
            if key not in looked_up:
                result.reason = 'Nutrition provider unavailable or timed out. Uncalculated ingredients remain unknown.'
                continue
            food = looked_up[key]
            if food is None:
                result.status, result.reason = 'unmatched', 'No unique food match with the same identity and preparation state.'
                continue
            result.food = food
            if ingredient.grams is None:
                matches = [portion for portion in food.portions if portion.unit == ingredient.normalized_unit]
                # No arbitrary density conversion and no selecting among conflicting portions.
                weights = {Decimal(str(p.gram_weight)) / Decimal(str(p.amount)) for p in matches}
                volume_evidence = ''
                if not matches and ingredient.normalized_unit in VOLUME_ML:
                    matches = [p for p in food.portions if p.unit in VOLUME_ML]
                    weights = {Decimal(str(p.gram_weight)) / Decimal(str(p.amount)) /
                               VOLUME_ML[p.unit] * VOLUME_ML[ingredient.normalized_unit] for p in matches}
                    volume_evidence = ' Volume ratios use US nutrition-label measures: tsp=5 ml, tbsp=15 ml, cup=240 ml.'
                # A counted clove retains its USDA portion mass when minced; this
                # does not authorize density assumptions for prepared volume units.
                count_prep_safe = (ingredient.normalized_unit == 'clove' and
                    ingredient.preparation in ('minced', 'crushed', 'chopped'))
                if len(weights) != 1 or (ingredient.preparation and not count_prep_safe):
                    result.status, result.reason = 'unconvertible', 'No unambiguous portion weight for this unit and preparation.'
                    continue
                ingredient.grams = float(Decimal(str(ingredient.quantity)) * next(iter(weights)))
                ingredient.conversion_evidence = f'USDA FDC {food.food_id}: {matches[0].description}, {matches[0].gram_weight} g per {matches[0].amount} {matches[0].unit}.' + volume_evidence
                ingredient.status, ingredient.reason = 'normalized', None
            factor = Decimal(str(ingredient.grams)) / Decimal(100)
            scaled = {name: float(Decimal(str(value)) * factor) if value is not None else None
                      for name, value in food.nutrients_per_100g.model_dump().items()}
            result.nutrients = NutrientValues(**scaled)
            result.status = 'calculated' if all(scaled[name] is not None for name in CORE) else 'partial'
            if result.status == 'partial':
                result.reason = 'The matched food record is missing a required nutrient.'
        totals, known, coverage = {}, {}, {}
        for name in NAMES:
            values = [getattr(result.nutrients, name) for result in results if getattr(result.nutrients, name) is not None]
            coverage[name] = len(values)
            known[name] = float(sum(Decimal(str(value)) for value in values)) if values else None
            totals[name] = known[name] if len(values) == len(ingredients) and ingredients else None
        per_serving = lambda values: NutrientValues(**{name: float(Decimal(str(value)) / servings) if value is not None else None for name, value in values.items()})
        status = ('verified' if ingredients and all(totals[name] is not None for name in CORE)
                  else 'partial' if any(value is not None for value in known.values()) else 'unavailable')
        return RecipeIntelligence(calculated_nutrition=CalculatedNutrition(
            totals=NutrientValues(**totals), per_serving=per_serving(totals), known_totals=NutrientValues(**known),
            known_per_serving=per_serving(known), coverage=coverage, ingredient_count=len(ingredients), servings=servings),
            nutrition_status=status, nutrition_sources=results,
            unmatched_ingredients=[result.ingredient.original_text for result in results if result.status in ('unmatched', 'unconvertible', 'unavailable')])
