from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.notification import Notification, UserNotificationPreference
from app.schemas.analysis import NotificationPrefUpdate
from typing import List

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("/")
async def get_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's recent notifications."""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    notifications = result.scalars().all()
    return [
        {
            "id": n.id,
            "type": n.type,
            "category": n.category,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at,
        }
        for n in notifications
    ]


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="الإشعار غير موجود")
    notif.is_read = True
    await db.flush()
    return {"message": "تم"}


@router.get("/preferences")
async def get_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get notification preferences."""
    result = await db.execute(
        select(UserNotificationPreference).where(UserNotificationPreference.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        prefs = UserNotificationPreference(user_id=user.id)
        db.add(prefs)
        await db.flush()
    return {
        "telegram_enabled": prefs.telegram_enabled,
        "telegram_chat_id": prefs.telegram_chat_id,
        "email_enabled": prefs.email_enabled,
        "web_enabled": prefs.web_enabled,
        "notify_opportunities": prefs.notify_opportunities,
        "notify_trades": prefs.notify_trades,
        "notify_daily_summary": prefs.notify_daily_summary,
    }


@router.patch("/preferences")
async def update_preferences(
    data: NotificationPrefUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update notification preferences."""
    result = await db.execute(
        select(UserNotificationPreference).where(UserNotificationPreference.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        prefs = UserNotificationPreference(user_id=user.id)
        db.add(prefs)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)

    await db.flush()
    return {"message": "تم تحديث الإعدادات"}
