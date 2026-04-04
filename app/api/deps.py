from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db, decode_token
from app.models import User, Guard, CompanyAdmin
from app.services import UserService
from app.services.guard import GuardService
from app.services.admin import CompanyAdminService

security = HTTPBearer()


# ============ User Dependencies ============

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token"""
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # If token has a role, make sure it's "user" or absent (legacy tokens)
    role = payload.get("role", "user")
    if role != "user":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: not a user token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await UserService.get_by_id(db, int(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    from app.models import UserStatus
    if current_user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )
    return current_user


async def require_subscription(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Require user to have active subscription"""
    has_subscription = await UserService.has_active_subscription(db, current_user.id)
    if not has_subscription:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active subscription required"
        )
    return current_user


# ============ Guard Dependencies ============

async def get_current_guard(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Guard:
    """Get current authenticated guard from JWT token"""
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access" or payload.get("role") != "guard":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid guard token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    guard_id = payload.get("sub")
    if not guard_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    guard = await GuardService.get_by_id(db, int(guard_id))
    if not guard:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guard not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if guard.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guard account is not active"
        )

    return guard


# ============ Company Admin Dependencies ============

async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> CompanyAdmin:
    """Get current authenticated company admin from JWT token"""
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access" or payload.get("role") != "company_admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    admin_id = payload.get("sub")
    if not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    admin = await CompanyAdminService.get_by_id(db, int(admin_id))
    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return admin


async def require_admin_owner(
    current_admin: CompanyAdmin = Depends(get_current_admin)
) -> CompanyAdmin:
    """Require admin to have 'owner' role"""
    if current_admin.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner privileges required"
        )
    return current_admin


# ============ WebSocket Dependencies ============

async def get_ws_current_user(
    db: AsyncSession,
    token: str
) -> Optional[User]:
    """Helper for WebSocket user authentication"""
    try:
        payload = decode_token(token)
        if not payload or payload.get("type") != "access" or payload.get("role", "user") != "user":
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
            
        return await UserService.get_by_id(db, int(user_id))
    except Exception:
        return None


async def get_ws_current_guard(
    db: AsyncSession,
    token: str
) -> Optional[Guard]:
    """Helper for WebSocket guard authentication"""
    try:
        payload = decode_token(token)
        if not payload or payload.get("type") != "access" or payload.get("role") != "guard":
            return None
        
        guard_id = payload.get("sub")
        if not guard_id:
            return None
            
        return await GuardService.get_by_id(db, int(guard_id))
    except Exception:
        return None
