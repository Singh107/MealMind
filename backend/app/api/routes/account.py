from uuid import UUID
from fastapi import APIRouter, Depends, Response
from app.core.auth import AuthenticatedUser, authenticated_user
from app.core.config import Settings, get_settings
from app.db.repositories import SavedRecipeRepository, ProfileRepository, UserPreferencesRepository
from app.schemas.persistence import SavedRecipeInput, PreferencesInput, ProfileInput

router = APIRouter(prefix='/api', tags=['account'])

def saved_repository(user: AuthenticatedUser = Depends(authenticated_user), settings: Settings = Depends(get_settings)):
    return SavedRecipeRepository(settings, user)

def preferences_repository(user: AuthenticatedUser = Depends(authenticated_user), settings: Settings = Depends(get_settings)):
    return UserPreferencesRepository(settings, user)

def profile_repository(user: AuthenticatedUser = Depends(authenticated_user), settings: Settings = Depends(get_settings)):
    return ProfileRepository(settings, user)

@router.post('/saved-recipes')
async def save_recipe(body: SavedRecipeInput, repository=Depends(saved_repository)):
    return await repository.create(body.recipe, body.source_id)

@router.get('/saved-recipes')
async def list_recipes(repository=Depends(saved_repository)):
    return await repository.list()

@router.get('/saved-recipes/{recipe_id}')
async def get_recipe(recipe_id: UUID, repository=Depends(saved_repository)):
    return await repository.get(recipe_id)

@router.delete('/saved-recipes/{recipe_id}', status_code=204)
async def delete_recipe(recipe_id: UUID, repository=Depends(saved_repository)):
    await repository.delete(recipe_id)
    return Response(status_code=204)

@router.get('/preferences')
async def get_preferences(repository=Depends(preferences_repository)):
    row = await repository.get()
    return PreferencesInput.model_validate({k: row[k] for k in PreferencesInput.model_fields} if row else {}).model_dump()

@router.put('/preferences')
async def put_preferences(body: PreferencesInput, repository=Depends(preferences_repository)):
    await repository.put(body.model_dump())
    return body

@router.get('/profile')
async def get_profile(repository=Depends(profile_repository)):
    row = await repository.get()
    return ProfileInput(display_name=row['display_name'] if row else '')

@router.put('/profile')
async def put_profile(body: ProfileInput, repository=Depends(profile_repository)):
    await repository.put(body.model_dump())
    return body
