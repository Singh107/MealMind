"""Compatibility entry point: uvicorn main:app still works from backend/."""
from app.main import app

__all__ = ["app"]
