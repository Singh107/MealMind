import asyncio
from fastapi import APIRouter, Depends, Request
from app.core.config import Settings, get_settings
from app.core.errors import GenerationError
from app.providers.vision import GeminiVisionProvider
from app.services.vision import IngredientVisionService, MAX_IMAGE_BYTES, FORMATS
from app.schemas.vision import ImageIngredientAnalysis

router = APIRouter(prefix='/api/vision', tags=['vision'])


def get_vision_service(settings: Settings = Depends(get_settings)):
    return IngredientVisionService(GeminiVisionProvider(settings), settings.generation_timeout_seconds)


async def read_image(request: Request):
    # Raw binary upload avoids multipart temp-file spooling. No filename/owner input.
    if request.query_params:
        raise GenerationError('vision_invalid_request', 'Image analysis accepts only an image body.', 422, False)
    mime = request.headers.get('content-type', '').split(';')[0].strip().lower()
    if mime not in FORMATS:
        raise GenerationError('vision_unsupported_image', 'Choose a JPEG, PNG or WebP image.', 415, False)
    data = bytearray()
    try:
        async with asyncio.timeout(15):
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_IMAGE_BYTES:
                    raise GenerationError('vision_image_too_large', 'Image file too large (max 5MB).', 413, False)
                data.extend(chunk)
    except TimeoutError as exc:
        raise GenerationError('vision_upload_timeout', 'Photo upload timed out. Please try again.', 408) from exc
    return bytes(data), mime


@router.post('/ingredients', response_model=ImageIngredientAnalysis)
async def analyze_ingredients(request: Request, service: IngredientVisionService = Depends(get_vision_service)):
    data, mime = await read_image(request)
    return await service.analyze(data, mime)
