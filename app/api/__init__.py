from fastapi import APIRouter
from app.api.routes import auth, user, emergency

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(emergency.router)
