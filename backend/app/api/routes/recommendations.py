from fastapi import APIRouter, Depends, Query
from app.core.auth import AuthenticatedUser, authenticated_user
from app.core.config import Settings, get_settings
from app.db.repositories import SavedRecipeRepository, UserPreferencesRepository
from app.db.pantry import PantryRepository
from app.schemas.persistence import PreferencesInput
from app.services.ranking import RankingService

router = APIRouter(prefix='/api/recommendations', tags=['recommendations'])

@router.get('/pantry')
async def pantry_recommendations(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000),
        user: AuthenticatedUser = Depends(authenticated_user), settings: Settings = Depends(get_settings)):
    rows = await SavedRecipeRepository(settings, user).list()
    pantry = await PantryRepository(settings, user).list()
    stored = await UserPreferencesRepository(settings, user).get()
    preferences = PreferencesInput.model_validate({k: stored[k] for k in PreferencesInput.model_fields} if stored else {})
    return RankingService().rank(rows, pantry, preferences, limit, offset)
