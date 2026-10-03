"""PostgREST repositories use the verified caller's JWT, never the service role.

Ownership filters provide defense in depth; database RLS is authoritative.
"""
import httpx
from app.core.auth import AuthenticatedUser
from app.core.config import Settings
from app.core.errors import GenerationError

class UserRepository:
    table: str

    def __init__(self, settings: Settings, user: AuthenticatedUser):
        self.settings, self.user = settings, user

    async def request(self, method, *, params=None, body=None, prefer='return=representation'):
        query = {'user_id': 'eq.' + self.user.id, **(params or {})}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.request(method,
                    self.settings.supabase_url.rstrip('/') + '/rest/v1/' + self.table,
                    params=query, json=body, headers={
                        'apikey': self.settings.supabase_anon_key.get_secret_value(),
                        'Authorization': 'Bearer ' + self.user.token, 'Prefer': prefer})
            if response.status_code == 401:
                raise GenerationError('auth_expired', 'Your session expired. Please sign in again.', 401, False)
            if response.status_code == 403:
                raise GenerationError('permission_denied', 'You do not have permission to access this data.', 403, False)
            if response.status_code == 409 and getattr(self, 'conflict_code', None) == 'pantry_duplicate':
                raise GenerationError('pantry_duplicate', 'This ingredient is already in your pantry. Edit the existing item instead.', 409, False)
            if response.status_code >= 400:
                raise GenerationError('supabase_unavailable', 'Account storage is unavailable. Please try again.', 503)
            return response.json() if response.content else []
        except (httpx.HTTPError, ValueError):
            raise GenerationError('supabase_unavailable', 'Account storage is unavailable. Please try again.', 503) from None

class SavedRecipeRepository(UserRepository):
    table = 'saved_recipes'

    async def list(self):
        rows = []
        while True:
            page = await self.request('GET', params={'select': '*', 'order': 'created_at.desc,id.desc',
                'limit': '500', 'offset': str(len(rows))})
            rows.extend(page)
            if len(page) < 500:
                return rows

    async def get(self, recipe_id):
        rows = await self.request('GET', params={'id': 'eq.' + str(recipe_id), 'select': '*'})
        if not rows:
            raise GenerationError('not_found', 'Saved recipe not found.', 404, False)
        return rows[0]

    async def create(self, recipe, source_id):
        # Unique (user_id, source_id) makes repeated saves/imports idempotent.
        rows = await self.request('POST', params={'on_conflict': 'user_id,source_id'},
            body={'user_id': self.user.id, 'source_id': source_id, 'recipe': recipe},
            prefer='resolution=ignore-duplicates,return=representation')
        if rows:
            return rows[0]
        rows = await self.request('GET', params={'source_id': 'eq.' + source_id, 'select': '*'})
        if not rows:
            raise GenerationError('supabase_unavailable', 'Saved recipe could not be read.', 503)
        return rows[0]

    async def delete(self, recipe_id):
        rows = await self.request('DELETE', params={'id': 'eq.' + str(recipe_id)})
        if not rows:
            raise GenerationError('not_found', 'Saved recipe not found.', 404, False)

class SingleUserRepository(UserRepository):
    async def get(self):
        rows = await self.request('GET', params={'select': '*'})
        return rows[0] if rows else None

    async def put(self, values):
        rows = await self.request('POST', params={'on_conflict': 'user_id'},
            body={**values, 'user_id': self.user.id},
            prefer='resolution=merge-duplicates,return=representation')
        return rows[0]

class ProfileRepository(SingleUserRepository):
    table = 'profiles'

class UserPreferencesRepository(SingleUserRepository):
    table = 'user_preferences'
