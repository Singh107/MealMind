"""Verify access tokens with Supabase Auth; never decode unverified claims."""
from dataclasses import dataclass, field
from uuid import UUID
import httpx
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import Settings, get_settings
from app.core.errors import GenerationError

bearer = HTTPBearer(auto_error=False)

@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    token: str = field(repr=False)

def require_supabase(settings: Settings):
    if not settings.supabase_url or not settings.supabase_anon_key.get_secret_value():
        raise GenerationError('auth_not_configured', 'Account storage is not configured yet.', 503, False)

async def authenticated_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                             settings: Settings = Depends(get_settings)) -> AuthenticatedUser:
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise GenerationError('auth_required', 'Sign in to access your account.', 401, False)
    require_supabase(settings)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(settings.supabase_url.rstrip('/') + '/auth/v1/user', headers={
                'apikey': settings.supabase_anon_key.get_secret_value(),
                'Authorization': 'Bearer ' + credentials.credentials})
        if response.status_code in (401, 403):
            raise GenerationError('auth_expired', 'Your session is invalid or expired. Please sign in again.', 401, False)
        if response.status_code != 200:
            raise GenerationError('supabase_unavailable', 'Account service is unavailable. Please try again.', 503)
        user_id = str(UUID(response.json()['id']))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise GenerationError('supabase_unavailable', 'Account service is unavailable. Please try again.', 503) from None
    return AuthenticatedUser(user_id, credentials.credentials)
