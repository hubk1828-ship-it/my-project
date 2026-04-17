from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.core.database import get_db
from app.core.security import hash_password
from app.api.deps import require_admin
from app.models.user import User
from app.models.trade import BotSettings
from app.models.notification import UserNotificationPreference
from app.schemas.user import UserCreate, UserResponse

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create new user (admin only)."""
    # Check existing
    existing = await db.execute(
        select(User).where((User.email == data.email) | (User.username == data.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="البريد أو اسم المستخدم مُستخدم بالفعل")

    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.flush()

    # Create default bot settings
    bot_settings = BotSettings(user_id=user.id)
    db.add(bot_settings)

    # Create default notification preferences
    notif_pref = UserNotificationPreference(user_id=user.id)
    db.add(notif_pref)

    await db.flush()
    return user


@router.patch("/users/{user_id}/toggle", response_model=UserResponse)
async def toggle_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Toggle user active/inactive (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="المستخدم غير موجود")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="لا يمكنك تعطيل نفسك")

    user.is_active = not user.is_active
    await db.flush()
    return user


@router.patch("/users/{user_id}/approve-auto-trade")
async def approve_auto_trade(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve/revoke auto-trade for a user (admin only)."""
    result = await db.execute(select(BotSettings).where(BotSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if not settings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="إعدادات البوت غير موجودة")

    settings.is_admin_approved = not settings.is_admin_approved
    await db.flush()
    return {"is_admin_approved": settings.is_admin_approved}
