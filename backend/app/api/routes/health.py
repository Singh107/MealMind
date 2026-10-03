from fastapi import APIRouter
router = APIRouter()


@router.get('/health')
async def health_check():
    return {'status': 'ok', 'message': 'MealMind API is healthy'}


@router.get('/')
async def root():
    return {'message': 'Welcome to MealMind API'}


@router.get('/api/test')
async def test_endpoint():
    return {'message': 'Backend is communicating with frontend!', 'data': {'test': True}}
