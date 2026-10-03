"""Bounded per-process admission controls; deployment edge controls still required."""
import asyncio
from collections import OrderedDict
from ipaddress import ip_address, ip_network
from time import monotonic
from uuid import uuid4
from starlette.responses import JSONResponse

EXPENSIVE = {'/api/recipes/generate', '/api/recipes/repair', '/api/vision/ingredients',
             '/api/vision/meal', '/api/nutrition/meal', '/api/ingredients/substitutions/preview'}
IMAGES = {'/api/vision/ingredients', '/api/vision/meal'}

class Admission:
    def __init__(self, settings, clock=monotonic):
        self.settings, self.clock = settings, clock
        self.buckets = OrderedDict()
        self.active = 0

    def admit(self, peer, expensive, weight=1):
        now = self.clock()
        # Fixed windows expire; arbitrary addresses cannot grow memory without bound.
        for key, (_, expires) in list(self.buckets.items()):
            if expires <= now: del self.buckets[key]
        limits = [(('peer',peer),120,60)]
        if expensive:
            limits += [(('ai',peer),self.settings.expensive_requests_per_minute,60),
                (('global','minute'),self.settings.global_expensive_per_minute,60),
                (('global','day'),self.settings.global_expensive_per_day,86400)]
        if len(self.buckets) + sum(key not in self.buckets for key,_,_ in limits) > 8192:
            return 60
        for key, maximum, seconds in limits:
            count, expires = self.buckets.get(key,(0,now+seconds))
            if count + weight > maximum: return max(1,int(expires-now)+1)
        for key, _, seconds in limits:
            count, expires = self.buckets.get(key,(0,now+seconds))
            self.buckets[key] = (count+weight,expires)
        return 0

class SecurityMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings
        self.admission = Admission(settings)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope,receive,send)
        async def secured_send(message):
            if message['type']=='http.response.start':
                message['headers'] += [(b'x-content-type-options',b'nosniff'),(b'referrer-policy',b'no-referrer'),
                    (b'x-frame-options',b'DENY'),(b'cache-control',b'no-store')]
            await send(message)
        async def reject(status,code,message,retry=None):
            headers={'X-Trace-ID':str(uuid4())}
            if retry: headers['Retry-After']=str(retry)
            response=JSONResponse({'error':{'code':code,'message':message,'retryable':status in (429,408),
                'trace_id':headers['X-Trace-ID'],'field_issues':[]}},status_code=status,headers=headers)
            await response(scope,receive,secured_send)
        path=scope.get('path','').rstrip('/')
        expensive=scope['method']=='POST' and path in EXPENSIVE
        peer=(scope.get('client') or ('unknown',0))[0]
        try:
            address=ip_address(peer)
            peer=str(ip_network(f'{address}/64',strict=False)) if address.version==6 else str(address)
        except ValueError: pass
        if scope['method']!='OPTIONS':
            retry=self.admission.admit(peer,expensive,2 if path=='/api/recipes/repair' else 1)
            if retry: return await reject(429,'rate_limited','Too many requests. Please try later.',retry)
        if expensive and self.admission.active>=self.settings.expensive_concurrency:
            return await reject(429,'service_busy','MealMind is busy. Please try shortly.',5)
        if expensive: self.admission.active+=1
        try:
            if scope['method'] in ('POST','PUT','PATCH'):
                limit=5*1024*1024 if path in IMAGES else 2*1024*1024+65536
                headers=dict(scope.get('headers',[]))
                try: length=int(headers.get(b'content-length',b'0'))
                except ValueError: return await reject(400,'invalid_request','Invalid request length.')
                if length<0: return await reject(400,'invalid_request','Invalid request length.')
                if length>limit: return await reject(413,'request_too_large','Request body is too large.')
                data=bytearray()
                try:
                    async with asyncio.timeout(15):
                        while True:
                            event=await receive()
                            if event['type']=='http.disconnect': return
                            chunk=event.get('body',b'')
                            if len(data)+len(chunk)>limit: return await reject(413,'request_too_large','Request body is too large.')
                            data.extend(chunk)
                            if not event.get('more_body',False): break
                except TimeoutError: return await reject(408,'request_timeout','Request upload timed out.')
                sent=False
                async def bounded_receive():
                    nonlocal sent
                    if not sent:
                        sent=True
                        return {'type':'http.request','body':bytes(data),'more_body':False}
                    return await receive()
                await self.app(scope,bounded_receive,secured_send)
            else: await self.app(scope,receive,secured_send)
        finally:
            if expensive: self.admission.active-=1
