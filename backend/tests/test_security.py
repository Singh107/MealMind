import asyncio
import base64
import json
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.core.config import Settings
from app.core.security import Admission, SecurityMiddleware, EXPENSIVE
from app.main import create_app, create_production_app
from app.providers.http_limits import bounded_request

def production(**changes):
    return Settings(**(dict(mealmind_environment='production',gemini_api_key='test-gemini',usda_api_key='test-usda',
        supabase_url='https://project.example.com',supabase_anon_key='sb_publishable_test',
        cors_origins=['https://app.example.com'],allowed_hosts=['api.example.com']) | changes))

class ConfigSecurityTests(unittest.TestCase):
    def test_production_factory_cannot_start_development(self):
        with patch('app.main.get_settings',return_value=Settings()),self.assertRaises(RuntimeError):
            create_production_app()
        with patch('app.main.get_settings',return_value=production()):
            self.assertIsNone(create_production_app().docs_url)
    def test_missing_production_configuration_fails_without_echo(self):
        with self.assertRaises(ValidationError) as caught:
            Settings(mealmind_environment='production',gemini_api_key='DO_NOT_ECHO')
        self.assertNotIn('DO_NOT_ECHO',str(caught.exception))
    def test_production_rejects_localhost_wildcards_and_mock(self):
        for change in [dict(cors_origins=['*']),dict(cors_origins=['http://localhost:3000']),dict(allowed_hosts=['*']),dict(dev_mock_ai=True)]:
            with self.subTest(change=change),self.assertRaises(ValidationError): production(**change)
    def test_public_key_not_service_secret(self):
        with self.assertRaises(ValidationError):production(supabase_anon_key='sb_secret_do_not_use')
        def token(role):
            return 'header.'+base64.urlsafe_b64encode(json.dumps({'role':role}).encode()).decode().rstrip('=')+'.signature'
        with self.assertRaises(ValidationError):production(supabase_anon_key=token('service_role'))
        self.assertIsNotNone(production(supabase_anon_key=token('anon')))
    def test_production_cors_host_and_no_docs(self):
        with TestClient(create_app(production()),base_url='https://api.example.com') as client:
            r=client.get('/health',headers={'Origin':'https://app.example.com'})
            self.assertEqual(r.headers['access-control-allow-origin'],'https://app.example.com')
            self.assertNotIn('access-control-allow-origin',client.get('/health',headers={'Origin':'https://evil.example.com'}).headers)
            self.assertEqual(client.get('/health',headers={'Host':'evil.example.com'}).status_code,400)
            self.assertEqual(client.get('/docs').status_code,404)
    def test_development_localhost_preserved(self):
        client=TestClient(create_app(Settings()))
        self.assertEqual(client.get('/health',headers={'Origin':'http://localhost:3000'}).headers['access-control-allow-origin'],'http://localhost:3000')
        self.assertNotIn('strict-transport-security',client.get('/health').headers)
    def test_headers_and_validation_do_not_reflect_input(self):
        client=TestClient(create_app(Settings()))
        response=client.post('/api/recipes/generate',json={'selected_ingredients':[],'secret':'DO_NOT_ECHO'})
        self.assertEqual(response.status_code,422)
        self.assertNotIn('DO_NOT_ECHO',response.text)
        self.assertEqual(response.headers['x-content-type-options'],'nosniff')
        self.assertEqual(response.headers['cache-control'],'no-store')
    def test_body_limit_precedes_validation_and_provider(self):
        client=TestClient(create_app(Settings()))
        response=client.post('/api/recipes/generate',content=b'x'*(3*1024*1024))
        self.assertEqual(response.status_code,413)
    def test_spoofed_forwarded_headers_do_not_change_rate_identity(self):
        client=TestClient(create_app(Settings(expensive_requests_per_minute=1)))
        self.assertEqual(client.post('/api/recipes/generate',json={}).status_code,422)
        response=client.post('/api/recipes/generate',json={},headers={'X-Forwarded-For':'192.0.2.123','Authorization':'Bearer invented'})
        self.assertEqual(response.status_code,429);self.assertIn('retry-after',response.headers)
    def test_expensive_paths_include_all_provider_entrypoints(self):
        self.assertEqual(len(EXPENSIVE),6)
        self.assertIn('/api/nutrition/meal',EXPENSIVE)
    def test_unknown_bearer_not_trusted_for_private_data(self):
        client=TestClient(create_app(Settings()))
        self.assertEqual(client.get('/api/pantry').status_code,401)

class AdmissionTests(unittest.TestCase):
    def test_window_recovers_and_global_limit_spans_peers(self):
        now=[0];gate=Admission(Settings(global_expensive_per_minute=2),lambda:now[0])
        self.assertEqual(gate.admit('a',True),0);self.assertEqual(gate.admit('b',True),0)
        self.assertGreater(gate.admit('c',True),0)
        now[0]=61;self.assertEqual(gate.admit('c',True),0)
    def test_daily_budget_and_repair_weight(self):
        now=[0];gate=Admission(Settings(global_expensive_per_day=2),lambda:now[0])
        self.assertEqual(gate.admit('a',True,2),0)
        now[0]=61;self.assertGreater(gate.admit('b',True),0)
    def test_bucket_memory_bound(self):
        gate=Admission(Settings())
        for index in range(9000):gate.admit(str(index),False)
        self.assertLessEqual(len(gate.buckets),8192)

class StreamSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_chunked_request_without_length_is_bounded(self):
        app=AsyncMock();middleware=SecurityMiddleware(app,Settings());messages=[]
        receive=AsyncMock(side_effect=[{'type':'http.request','body':b'x'*(1024*1024),'more_body':True}]*3)
        async def send(message):messages.append(message)
        await middleware({'type':'http','method':'POST','path':'/api/recipes/generate','headers':[],'client':('127.0.0.1',1)},receive,send)
        self.assertEqual(messages[0]['status'],413);app.assert_not_awaited()
    async def test_concurrent_provider_admission_and_release(self):
        entered=asyncio.Event();finish=asyncio.Event()
        async def app(scope,receive,send):
            entered.set();await finish.wait()
        middleware=SecurityMiddleware(app,Settings(expensive_concurrency=1));sent=[]
        async def send(message):sent.append(message)
        scope={'type':'http','method':'POST','path':'/api/vision/meal','headers':[],'client':('127.0.0.1',1)}
        first=asyncio.create_task(middleware(scope,AsyncMock(return_value={'type':'http.request','body':b''}),send))
        await entered.wait()
        await middleware(scope,AsyncMock(),send)
        self.assertEqual(sent[0]['status'],429)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):await first
        self.assertEqual(middleware.admission.active,0)
    async def test_provider_response_limit_and_success(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*20))) as client:
            with self.assertRaises(httpx.RequestError):await bounded_request(client,'GET','https://provider.example.com',max_bytes=10)
            result=await bounded_request(client,'GET','https://provider.example.com',max_bytes=30)
            self.assertEqual(result.content,b'x'*20)
