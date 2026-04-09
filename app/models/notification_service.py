"""
Notification Routes for Kabaza
Handles device token registration, notification preferences, and inbox
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.db.database import get_db
from app.auth.jwt import get_current_user
from app.models.notification import (
    DeviceToken, Notification, NotificationPreference,
    NotificationType, DeviceType
)
from app.models.sql_models import User

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ============================================
# SCHEMAS
# ============================================

class RegisterDeviceRequest(BaseModel):
    token: str = Field(..., description="FCM/APNS device token")
    device_type: str = Field(..., pattern="^(android|ios|web)$")
    device_name: Optional[str] = None
    device_model: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None


class NotificationPreferenceUpdate(BaseModel):
    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    ride_updates: Optional[bool] = None
    payment_updates: Optional[bool] = None
    promotional: Optional[bool] = None
    chat_messages: Optional[bool] = None
    driver_nearby: Optional[bool] = None
    earnings_updates: Optional[bool] = None
    system_alerts: Optional[bool] = None


class NotificationResponse(BaseModel):
    id: int
    notification_id: str
    title: str
    body: str
    notification_type: str
    priority: str
    data: Optional[dict] = None
    image_url: Optional[str] = None
    action_url: Optional[str] = None
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class NotificationCountResponse(BaseModel):
    total: int
    unread: int


class DeviceTokenResponse(BaseModel):
    id: int
    token: str
    device_type: str
    device_name: Optional[str] = None
    is_active: bool
    last_used_at: datetime
    created_at: datetime


# ============================================
# DEVICE TOKEN ENDPOINTS
# ============================================

@router.post("/devices", response_model=DeviceTokenResponse)
async def register_device(
    request: RegisterDeviceRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Register a device token for push notifications
    """
    user_id = int(current_user.get("sub"))
    
    # Check if token already exists
    existing = db.query(DeviceToken).filter(
        DeviceToken.token == request.token
    ).first()
    
    if existing:
        # Update existing token
        existing.user_id = user_id
        existing.device_type = DeviceType(request.device_type)
        existing.device_name = request.device_name
        existing.device_model = request.device_model
        existing.os_version = request.os_version
        existing.app_version = request.app_version
        existing.is_active = True
        existing.last_used_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    
    # Create new token
    device = DeviceToken(
        user_id=user_id,
        token=request.token,
        device_type=DeviceType(request.device_type),
        device_name=request.device_name,
        device_model=request.device_model,
        os_version=request.os_version,
        app_version=request.app_version,
        is_active=True
    )
    
    db.add(device)
    db.commit()
    db.refresh(device)
    
    return device


@router.delete("/devices/{token}")
async def unregister_device(
    token: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Unregister a device token
    """
    user_id = int(current_user.get("sub"))
    
    device = db.query(DeviceToken).filter(
        DeviceToken.token == token,
        DeviceToken.user_id == user_id
    ).first()
    
    if device:
        device.is_active = False
        db.commit()
        return {"success": True, "message": "Device unregistered"}
    
    raise HTTPException(status_code=404, detail="Device not found")


@router.get("/devices", response_model=List[DeviceTokenResponse])
async def get_devices(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all registered devices for current user
    """
    user_id = int(current_user.get("sub"))
    
    devices = db.query(DeviceToken).filter(
        DeviceToken.user_id == user_id,
        DeviceToken.is_active == True
    ).all()
    
    return devices


# ============================================
# NOTIFICATION PREFERENCES ENDPOINTS
# ============================================

@router.get("/preferences")
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get notification preferences for current user
    """
    user_id = int(current_user.get("sub"))
    
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user_id
    ).first()
    
    if not prefs:
        # Create default preferences
        prefs = NotificationPreference(user_id=user_id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    
    return prefs


@router.put("/preferences")
async def update_preferences(
    request: NotificationPreferenceUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update notification preferences
    """
    user_id = int(current_user.get("sub"))
    
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user_id
    ).first()
    
    if not prefs:
        prefs = NotificationPreference(user_id=user_id)
        db.add(prefs)
    
    # Update fields
    for key, value in request.dict(exclude_unset=True).items():
        setattr(prefs, key, value)
    
    db.commit()
    db.refresh(prefs)
    
    return {"success": True, "preferences": prefs}


# ============================================
# NOTIFICATION INBOX ENDPOINTS
# ============================================

@router.get("/inbox", response_model=List[NotificationResponse])
async def get_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    notification_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's notification inbox
    """
    user_id = int(current_user.get("sub"))
    
    query = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.expires_at > datetime.utcnow()
    )
    
    if unread_only:
        query = query.filter(Notification.is_read == False)
    
    if notification_type:
        query = query.filter(Notification.notification_type == notification_type)
    
    notifications = query.order_by(
        Notification.created_at.desc()
    ).offset(offset).limit(limit).all()
    
    return notifications


@router.get("/inbox/count", response_model=NotificationCountResponse)
async def get_notification_count(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get total and unread notification count
    """
    user_id = int(current_user.get("sub"))
    
    total = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.expires_at > datetime.utcnow()
    ).count()
    
    unread = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
        Notification.expires_at > datetime.utcnow()
    ).count()
    
    return NotificationCountResponse(total=total, unread=unread)


@router.put("/inbox/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark a notification as read
    """
    user_id = int(current_user.get("sub"))
    
    notification = db.query(Notification).filter(
        Notification.notification_id == notification_id,
        Notification.user_id == user_id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.commit()
    
    return {"success": True}


@router.put("/inbox/read-all")
async def mark_all_as_read(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark all notifications as read
    """
    user_id = int(current_user.get("sub"))
    
    db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False
    ).update({
        "is_read": True,
        "read_at": datetime.utcnow()
    })
    
    db.commit()
    
    return {"success": True}


@router.delete("/inbox/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a notification
    """
    user_id = int(current_user.get("sub"))
    
    notification = db.query(Notification).filter(
        Notification.notification_id == notification_id,
        Notification.user_id == user_id
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    db.delete(notification)
    db.commit()
    
    return {"success": True}


@router.delete("/inbox/clear-all")
async def clear_all_notifications(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Clear all notifications
    """
    user_id = int(current_user.get("sub"))
    
    db.query(Notification).filter(
        Notification.user_id == user_id
    ).delete()
    
    db.commit()
    
    return {"success": True}


# ============================================
# TEST ENDPOINTS (Development Only)
# ============================================

@router.post("/test/send")
async def test_send_notification(
    title: str = "Test Notification",
    body: str = "This is a test notification from Kabaza!",
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Test endpoint to send a notification to current user
    (Development only - remove in production)
    """
    from app.services.notification_service import NotificationService, NotificationType, NotificationPriority
    
    user_id = int(current_user.get("sub"))
    
    service = NotificationService()
    result = await service.send_to_user(
        db=db,
        user_id=user_id,
        title=title,
        body=body,
        notification_type=NotificationType.SYSTEM_ALERT,
        data={"test": True, "timestamp": datetime.utcnow().isoformat()},
        priority=NotificationPriority.MEDIUM,
        save_to_inbox=True,
        send_push=True
    )
    
    return result