from fastapi import APIRouter
from app.api.routes import auth, user, emergency, guard_auth, guard, guard_calls, admin_auth, admin, extras, routing

api_router = APIRouter(prefix="/api/v1")

# User app routes
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(emergency.router)
api_router.include_router(extras.router)

# Guard app routes
api_router.include_router(guard_auth.router)
api_router.include_router(guard.router)
api_router.include_router(guard_calls.router)
api_router.include_router(routing.router)

# Admin web panel routes
api_router.include_router(admin_auth.router)
api_router.include_router(admin.router)
