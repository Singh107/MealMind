from uuid import UUID
from fastapi import APIRouter, Depends, Response
from app.core.auth import AuthenticatedUser, authenticated_user
from app.core.config import Settings, get_settings
from app.db.pantry import PantryRepository
from app.schemas.pantry import PantryInput, PantryItem, CompatibilityInput, PantryCompatibility
from app.services.pantry import PantryService

router = APIRouter(prefix='/api/pantry', tags=['pantry'])


def pantry_service(user: AuthenticatedUser = Depends(authenticated_user), settings: Settings = Depends(get_settings)):
    return PantryService(PantryRepository(settings, user))


@router.get('', response_model=list[PantryItem])
async def list_items(service=Depends(pantry_service)):
    return await service.list()


@router.post('', response_model=PantryItem, status_code=201)
async def create_item(body: PantryInput, service=Depends(pantry_service)):
    return await service.save(body)


@router.post('/compatibility', response_model=PantryCompatibility)
async def compatibility(body: CompatibilityInput, service=Depends(pantry_service)):
    return await service.compatibility(body.ingredients)


@router.get('/{item_id}', response_model=PantryItem)
async def get_item(item_id: UUID, service=Depends(pantry_service)):
    return await service.get(item_id)


@router.put('/{item_id}', response_model=PantryItem)
async def update_item(item_id: UUID, body: PantryInput, service=Depends(pantry_service)):
    return await service.save(body, item_id)


@router.delete('/{item_id}', status_code=204)
async def delete_item(item_id: UUID, service=Depends(pantry_service)):
    await service.repository.delete(item_id)
    return Response(status_code=204)
