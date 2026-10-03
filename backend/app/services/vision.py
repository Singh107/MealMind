import asyncio
from io import BytesIO
import warnings
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError
from app.core.errors import GenerationError
from app.providers.vision import VisionProvider
from app.schemas.vision import VisionProposal, IngredientDetection, ImageIngredientAnalysis
from app.services.normalization import IngredientNormalizationService
from app.services.pantry import pantry_identity

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
FORMATS = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}


def prepare_image(data: bytes, mime: str) -> bytes:
    if mime not in FORMATS:
        raise GenerationError('vision_unsupported_image', 'Choose a JPEG, PNG or WebP image.', 415, False)
    if not data:
        raise GenerationError('vision_empty_image', 'Choose a non-empty image.', 422, False)
    if len(data) > MAX_IMAGE_BYTES:
        raise GenerationError('vision_image_too_large', 'Image file too large (max 5MB).', 413, False)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format != FORMATS[mime] or source.width * source.height > MAX_PIXELS or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError()
                source.verify()
            with Image.open(BytesIO(data)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source).convert('RGBA')
                oriented.thumbnail((2048, 2048))
                # Fresh canvas: no EXIF, ICC, text chunks or original encoded payload.
                clean = Image.new('RGB', oriented.size, 'white')
                clean.paste(oriented, mask=oriented.getchannel('A'))
                out = BytesIO()
                clean.save(out, format='JPEG', quality=90)
                return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise GenerationError('vision_invalid_image', 'This image is invalid, animated, or too large in dimensions. Choose another photo.', 422, False) from exc


class IngredientVisionService:
    def __init__(self, provider: VisionProvider, timeout=45):
        self.provider, self.timeout = provider, timeout

    async def analyze(self, data: bytes, mime: str):
        image = await asyncio.to_thread(prepare_image, data, mime)
        try:
            async with asyncio.timeout(self.timeout):
                raw = await self.provider.analyze(image, 'image/jpeg')
            proposal = VisionProposal.model_validate_json(raw)
        except TimeoutError as exc:
            raise GenerationError('vision_timeout', 'Ingredient analysis timed out. Please try again.', 504) from exc
        except (ValidationError, ValueError, TypeError) as exc:
            raise GenerationError('vision_invalid_output', 'The image could not be read reliably. Please try another photo.') from exc
        normalizer = IngredientNormalizationService()
        detections, seen = [], {}
        for item in proposal.detections:
            name = item.display_name + (f', {item.visible_state}' if item.visible_state else '')
            normalized = normalizer.normalize(name, 1, 'g')  # Neutral normalization basis, never a detected quantity.
            identity = pantry_identity(name)
            conflict = normalized.reason == 'Conflicting food preparation states.'
            status = 'conflicting' if conflict else identity['identity_status']
            detection = IngredientDetection(**item.model_dump(), normalized_name=identity['normalized_name'],
                canonical_name=normalized.canonical_name, food_state=normalized.food_state, identity_status=status)
            key = identity['identity_key']
            if status == 'recognized' and key in seen:
                prior = seen[key]
                prior.merged_count += 1
                prior.confidence = min((prior.confidence, detection.confidence), key=['low', 'medium', 'high'].index)
                prior.uncertainty = 'Repeated suggestions combined; review the ingredient and visible state.'
            else:
                detections.append(detection)
                if status == 'recognized':
                    seen[key] = detection
        return ImageIngredientAnalysis(analysis_id=str(uuid4()), detections=detections,
            warnings=['Suggestions need your review. Confidence is the model\'s self-assessment, not a measured probability.',
                      'Photos do not establish quantities, nutrition, allergens, freshness or food safety.'],
            provider=self.provider.name, model=self.provider.model)
