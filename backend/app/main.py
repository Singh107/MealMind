import logging
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.core.security import SecurityMiddleware
from app.api.routes import health, recipes, account, pantry, recommendations, substitutions, vision, meal
from app.core.config import Settings, get_settings
from app.core.errors import ErrorInfo, ErrorResponse, FieldIssue, GenerationError

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    # USDA requires a key in the URL; HTTP client INFO/DEBUG logging must not expose it.
    for name in ('httpx', 'httpcore'):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger('uvicorn.error').info('Recipe provider: %s',
        'Development fixture' if settings.dev_mock_ai else 'Gemini')
    production = settings.mealmind_environment == 'production'
    app = FastAPI(title='MealMind API', version='0.2.0', debug=False,
                  docs_url=None if production else '/docs', redoc_url=None if production else '/redoc',
                  openapi_url=None if production else '/openapi.json')
    app.dependency_overrides[get_settings] = lambda: settings

    @app.middleware('http')
    async def trace_request(request: Request, call_next):
        request.state.trace_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception as exc:
            response = await unexpected_error(request, exc)
        response.headers['X-Trace-ID'] = request.state.trace_id
        return response

    def error_response(request, code, message, status, retryable, issues=None):
        return JSONResponse(status_code=status, content=ErrorResponse(error=ErrorInfo(
            code=code, message=message, retryable=retryable,
            trace_id=request.state.trace_id, field_issues=issues or [])).model_dump())

    @app.exception_handler(GenerationError)
    async def generation_error(request: Request, exc: GenerationError):
        return error_response(request, exc.code, exc.message, exc.status, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        issues = [FieldIssue(field='.'.join(map(str, error['loc'][1:])), message=error['msg']) for error in exc.errors()]
        return error_response(request, 'invalid_request', 'Please check your recipe preferences.', 422, False, issues)

    async def unexpected_error(request: Request, exc: Exception):
        # Never log raw provider exceptions, request data or API keys.
        logger.error('Unexpected request failure trace_id=%s type=%s', request.state.trace_id, type(exc).__name__)
        return error_response(request, 'internal_error', 'Recipe generation failed unexpectedly. Please retry.', 500, True)

    app.include_router(health.router)
    app.include_router(recipes.router)
    app.include_router(account.router)
    app.include_router(pantry.router)
    app.include_router(recommendations.router)
    app.include_router(substitutions.router)
    app.include_router(vision.router)
    app.include_router(meal.router)
    app.add_middleware(SecurityMiddleware, settings=settings)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts, www_redirect=False)
    # Outermost so even unexpected failures have CORS and trace headers.
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=False, allow_methods=['GET', 'POST', 'PUT', 'DELETE'],
                       allow_headers=['Content-Type', 'Authorization'], expose_headers=['X-Trace-ID','Retry-After'])
    return app


def create_production_app() -> FastAPI:
    """Explicit deployment target; a missing environment flag cannot start development."""
    settings = get_settings()
    if settings.mealmind_environment != 'production':
        raise RuntimeError('Production startup requires MEALMIND_ENVIRONMENT=production.')
    return create_app(settings)


app = create_app()
