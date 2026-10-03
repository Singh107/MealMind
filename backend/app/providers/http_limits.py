"""Stream decoded provider responses into a bounded buffer; never log payloads."""
import httpx

async def bounded_request(client, method, url, *, max_bytes=4*1024*1024, **kwargs):
    async with client.stream(method, url, **kwargs) as response:
        content=bytearray()
        async for chunk in response.aiter_bytes():
            if len(content)+len(chunk)>max_bytes:
                raise httpx.RequestError('Provider response exceeded the configured size limit.')
            content.extend(chunk)
        return httpx.Response(response.status_code,headers={k:v for k,v in response.headers.items()
            if k.lower() not in ('content-encoding','content-length')},content=bytes(content),request=response.request)
