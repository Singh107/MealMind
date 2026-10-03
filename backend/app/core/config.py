import os
import base64
import json
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from typing import Literal
from urllib.parse import urlsplit


class Settings(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    mealmind_environment: Literal['development', 'production'] = 'development'
    dev_mock_ai: bool = False
    supabase_url: str = ''
    supabase_anon_key: SecretStr = SecretStr('')
    gemini_api_key: SecretStr = SecretStr('')
    gemini_model: str = Field(default='gemini-3.1-flash-lite', pattern=r'^[a-zA-Z0-9._-]+$')
    generation_timeout_seconds: float = Field(default=45, gt=0, le=45)
    max_repair_attempts: int = Field(default=2, ge=0, le=2)
    repair_timeout_seconds: float = Field(default=100, gt=0, le=120)
    max_output_tokens: int = Field(default=4096, ge=512, le=8192)
    usda_api_key: SecretStr = SecretStr('')
    nutrition_timeout_seconds: float = Field(default=10, gt=0, le=15)
    nutrition_cache_ttl_seconds: int = Field(default=86400, ge=1, le=604800)
    nutrition_cache_max_entries: int = Field(default=256, ge=1, le=10000)
    allowed_hosts: list[str] = ['localhost', '127.0.0.1', 'testserver']
    expensive_requests_per_minute: int = Field(default=10, ge=1, le=60)
    global_expensive_per_minute: int = Field(default=60, ge=1, le=300)
    global_expensive_per_day: int = Field(default=500, ge=1, le=10000)
    expensive_concurrency: int = Field(default=4, ge=1, le=16)
    cors_origins: list[str] = ['http://localhost:3000', 'http://127.0.0.1:3000',
                               'http://localhost:3001', 'http://127.0.0.1:3001']


    @model_validator(mode='after')
    def development_fixture_only(self):
        if self.dev_mock_ai and (self.mealmind_environment != 'development' or 'mealmind_environment' not in self.model_fields_set):
            raise ValueError('MEALMIND_DEV_MOCK_AI requires MEALMIND_ENVIRONMENT=development.')
        if self.mealmind_environment == 'production':
            required = (self.gemini_api_key, self.usda_api_key, self.supabase_anon_key)
            if any(not value.get_secret_value().strip() for value in required) or not self.supabase_url:
                raise ValueError('Production requires Gemini, USDA and Supabase configuration.')
            origins = [urlsplit(value) for value in self.cors_origins]
            if not origins or any(value.scheme != 'https' or not value.hostname or value.hostname in ('localhost','127.0.0.1') or value.path or value.query or value.fragment or value.username for value in origins):
                raise ValueError('Production requires explicit HTTPS CORS origins without paths.')
            if not self.allowed_hosts or any('*' in host or host in ('localhost','127.0.0.1','testserver') or '/' in host or ':' in host for host in self.allowed_hosts):
                raise ValueError('Production requires explicit public ALLOWED_HOSTS.')
            if urlsplit(self.supabase_url).scheme != 'https':
                raise ValueError('Production Supabase URL must use HTTPS.')
            key = self.supabase_anon_key.get_secret_value()
            public_key = key.startswith('sb_publishable_')
            try:
                payload = key.split('.')[1]
                public_key = public_key or json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4))).get('role') == 'anon'
            except (IndexError, ValueError, TypeError, AttributeError):
                pass
            if not public_key or key.startswith('sb_secret_'):
                raise ValueError('Supabase ordinary requests require a public key.')
        return self


@lru_cache
def get_settings() -> Settings:
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    values = {}
    for field, env in [('supabase_url', 'SUPABASE_URL'), ('supabase_anon_key', 'SUPABASE_ANON_KEY'),
                       ('dev_mock_ai', 'MEALMIND_DEV_MOCK_AI'),
                       ('mealmind_environment', 'MEALMIND_ENVIRONMENT'), ('gemini_api_key', 'GEMINI_API_KEY'), ('gemini_model', 'GEMINI_MODEL'),
                       ('generation_timeout_seconds', 'GENERATION_TIMEOUT_SECONDS'),
                       ('max_repair_attempts', 'MAX_REPAIR_ATTEMPTS'),
                       ('repair_timeout_seconds', 'REPAIR_TIMEOUT_SECONDS'),
                       ('max_output_tokens', 'GEMINI_MAX_OUTPUT_TOKENS'), ('usda_api_key', 'USDA_API_KEY'),
                       ('nutrition_timeout_seconds', 'NUTRITION_TIMEOUT_SECONDS'),
                       ('nutrition_cache_ttl_seconds', 'NUTRITION_CACHE_TTL_SECONDS'),
                       ('nutrition_cache_max_entries', 'NUTRITION_CACHE_MAX_ENTRIES')]:
        if env in os.environ:
            values[field] = os.environ[env]
    if 'CORS_ORIGINS' in os.environ:
        values['cors_origins'] = [v.strip() for v in os.environ['CORS_ORIGINS'].split(',') if v.strip()]
    if 'ALLOWED_HOSTS' in os.environ:
        values['allowed_hosts'] = [v.strip() for v in os.environ['ALLOWED_HOSTS'].split(',') if v.strip()]
    for field in ('expensive_requests_per_minute','global_expensive_per_minute','global_expensive_per_day','expensive_concurrency'):
        if field.upper() in os.environ:
            values[field] = os.environ[field.upper()]
    return Settings(**values)
