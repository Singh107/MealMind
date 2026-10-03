from app.core.errors import GenerationError
from app.db.repositories import UserRepository


class PantryRepository(UserRepository):
    table = 'pantry_items'
    conflict_code = 'pantry_duplicate'

    async def list(self):
        rows = []
        while True:
            page = await self.request('GET', params={'select': '*', 'order': 'created_at.asc,id.asc',
                                                     'limit': '500', 'offset': str(len(rows))})
            rows.extend(page)
            if len(page) < 500:
                return rows

    async def get(self, item_id):
        rows = await self.request('GET', params={'id': 'eq.' + str(item_id)})
        if not rows:
            raise GenerationError('pantry_not_found', 'Pantry item no longer exists.', 404, False)
        return rows[0]

    async def by_identity(self, identity_key):
        rows = await self.request('GET', params={'identity_key': 'eq.' + identity_key})
        return rows[0] if rows else None

    async def save(self, values, item_id=None):
        if item_id is None:
            rows = await self.request('POST', body={**values, 'user_id': self.user.id})
        else:
            rows = await self.request('PATCH', params={'id': 'eq.' + str(item_id)}, body=values)
        if not rows:
            raise GenerationError('pantry_not_found', 'Pantry item no longer exists.', 404, False)
        return rows[0]

    async def delete(self, item_id):
        rows = await self.request('DELETE', params={'id': 'eq.' + str(item_id)})
        if not rows:
            raise GenerationError('pantry_not_found', 'Pantry item no longer exists.', 404, False)
