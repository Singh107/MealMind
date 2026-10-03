"""Bounded TTL cache of public food records; no private recipes or request profiles."""
from collections import OrderedDict
from time import monotonic
from typing import Protocol
from app.schemas.intelligence import FoodRecord, NormalizedIngredient
from app.providers.nutrition import NutritionProvider
from app.providers.usda import match_key


class FoodCache(Protocol):
    def get(self, key: str) -> FoodRecord | None: ...
    def put(self, key: str, value: FoodRecord) -> None: ...


class InMemoryFoodCache:
    def __init__(self, ttl_seconds: float = 86400, max_entries: int = 256, clock=monotonic):
        self.ttl, self.max_entries, self.clock = ttl_seconds, max_entries, clock
        self.entries: OrderedDict[str, tuple[float, FoodRecord]] = OrderedDict()

    def get(self, key):
        entry = self.entries.get(key)
        if entry is None:
            return None
        expires, food = entry
        if self.clock() >= expires:
            del self.entries[key]
            return None
        self.entries.move_to_end(key)
        return food.model_copy(deep=True)

    def put(self, key, value):
        self.entries[key] = (self.clock() + self.ttl, value.model_copy(deep=True))
        self.entries.move_to_end(key)
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)


class CachedNutritionProvider:
    def __init__(self, provider: NutritionProvider, cache: FoodCache):
        self.provider, self.cache = provider, cache

    async def lookup(self, ingredient: NormalizedIngredient):
        identity = ' '.join(match_key(ingredient.name))
        key = f'usda-match-v5:{identity}:{ingredient.food_state or "unspecified"}'
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        food = await self.provider.lookup(ingredient)
        if food is not None:
            self.cache.put(key, food)
        # Failures/unmatched results are not persisted, allowing recovery immediately.
        return food
