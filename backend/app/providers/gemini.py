from app.providers.http_limits import bounded_request
import json
import logging
import asyncio
import httpx
from app.core.config import Settings
from app.core.errors import GenerationError
from app.providers.prompts import RECIPE_SYSTEM_PROMPT
from app.schemas.recipes import RecipeCandidate, RecipeGenerationRequest

logger = logging.getLogger(__name__)
SAFE_STATUSES = {'INTERNAL', 'UNAVAILABLE', 'RESOURCE_EXHAUSTED', 'INVALID_ARGUMENT',
                 'NOT_FOUND', 'PERMISSION_DENIED', 'UNAUTHENTICATED', 'DEADLINE_EXCEEDED'}


def safe_status(response: httpx.Response) -> str:
    try:
        value = response.json().get('error', {}).get('status')
        return value if isinstance(value, str) and value in SAFE_STATUSES else 'UNKNOWN'
    except (ValueError, AttributeError, TypeError):
        return 'UNKNOWN'


class GeminiRecipeProvider:
    name = 'gemini'

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.model = settings.gemini_model
        self.transport = transport

    async def generate(self, request: RecipeGenerationRequest) -> str:
        return await self._request(RECIPE_SYSTEM_PROMPT, request.model_dump_json())

    async def repair(self, payload: dict) -> str:
        from app.providers.prompts import REPAIR_SYSTEM_PROMPT
        return await self._request(REPAIR_SYSTEM_PROMPT, json.dumps(payload))

    async def _request(self, instruction: str, content: str) -> str:
        key = self.settings.gemini_api_key.get_secret_value().strip()
        if not key:
            raise GenerationError('provider_not_configured', 'Recipe generation is unavailable.', 503, False)
        payload = {
            'systemInstruction': {'parts': [{'text': instruction + '\nRequired JSON schema: ' +
                                                     json.dumps(RecipeCandidate.model_json_schema())}]},
            'contents': [{'role': 'user', 'parts': [{'text': content}]}],
            'generationConfig': {'maxOutputTokens': self.settings.max_output_tokens,
                                 'responseMimeType': 'application/json'},
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.generation_timeout_seconds,
                                         transport=self.transport) as client:
                for attempt in range(2):
                    response = await bounded_request(client, 'POST',
                        f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent',
                        headers={'x-goog-api-key': key}, json=payload)
                    if attempt == 0 and (response.status_code, safe_status(response)) in ((503, 'UNAVAILABLE'), (500, 'INTERNAL')):
                        # RecipeService's existing total deadline includes this backoff
                        # and both attempts. Never retry quota/auth/schema/output errors.
                        await asyncio.sleep(.3)
                        continue
                    break
        except httpx.TimeoutException as exc:
            raise GenerationError('provider_timeout', 'Recipe generation timed out. Please try again.', 504) from exc
        except httpx.RequestError as exc:
            raise GenerationError('provider_unavailable', 'The recipe provider could not be reached.', 503) from exc
        if response.is_error:
            # Status codes only: never messages, URLs, keys or request/response bodies.
            logger.warning('Gemini request rejected http_status=%s upstream_status=%s attempts=%s', response.status_code, safe_status(response), attempt + 1)
        if response.status_code in (401, 403):
            raise GenerationError('provider_authentication_failed',
                                  'The recipe provider rejected its backend credentials.', 503, False)
        if response.status_code == 429:
            raise GenerationError('provider_rate_limited', 'The recipe provider is busy or its quota is exhausted. Try later.', 429)
        if response.is_error:
            raise GenerationError('provider_failure', 'The recipe provider could not complete the request.',
                                  502, response.status_code >= 500)
        try:
            body = response.json()
            candidates = body.get('candidates', [])
            if not candidates:
                raise GenerationError('no_recipe_generated', 'No recipe was returned. Review your ingredients and preferences.', 422, False)
            candidate = candidates[0]
            if candidate.get('finishReason') != 'STOP':
                raise GenerationError('incomplete_provider_output', 'The provider did not return a complete recipe.')
            text = ''.join(part['text'] for part in candidate['content']['parts'] if not part.get('thought') and 'text' in part)
            if not text.strip():
                raise ValueError('Empty content')
            return text
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise GenerationError('invalid_provider_output', 'The provider returned an unreadable recipe. Please retry.') from exc
