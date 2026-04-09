"""
Notification Routes for Kabaza
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.db.database import get_db
from app.auth.jwt import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ============================================
# SCHEMAS
# ============================================

class RegisterDeviceRequest(BaseModel):
    token: str = Field(..., description="FCM/APNS device token")
    device_type: str = Field(..., pattern="^(android|ios|web)$")
    device_name: Optional[str] = None


class NotificationResponse(BaseModel):
    id: int
    title: str
    body: str
    is_read: bool
    created_at: datetime


# ============================================
# ENDPOINTS
# ============================================

@router.post("/devices")
async def register_device(
    request: RegisterDeviceRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Register a device token for push notifications"""
    return {"success": True, "message": "Device registered"}


@router.get("/inbox")
async def get_notifications(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's notification inbox"""
    return {"notifications": [], "total": 0, "unread": 0}


@router.put("/inbox/read-all")
async def mark_all_as_read(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark all notifications as read"""
    return {"success": True}


@router.get("/preferences")
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get notification preferences"""
    return {
        "push_enabled": True,
        "ride_updates": True,
        "payment_updates": True,
        "promotional": True
    }