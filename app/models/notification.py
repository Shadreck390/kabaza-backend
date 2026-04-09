"""
Notification Models for Kabaza
Includes push notification tokens, notification history, and preferences
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base
import enum


class NotificationType(str, enum.Enum):
    """Types of notifications"""
    RIDE_REQUEST = "ride_request"
    RIDE_ACCEPTED = "ride_accepted"
    RIDE_ARRIVED = "ride_arrived"
    RIDE_STARTED = "ride_started"
    RIDE_COMPLETED = "ride_completed"
    RIDE_CANCELLED = "ride_cancelled"
    PAYMENT_RECEIVED = "payment_received"
    PAYOUT_COMPLETED = "payout_completed"
    PROMO_OFFER = "promo_offer"
    SYSTEM_ALERT = "system_alert"
    CHAT_MESSAGE = "chat_message"
    DRIVER_NEARBY = "driver_nearby"
    EARNINGS_UPDATE = "earnings_update"
    VERIFICATION_UPDATE = "verification_update"


class NotificationPriority(str, enum.Enum):
    """Notification priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class DeviceType(str, enum.Enum):
    """Device types for push notifications"""
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


class DeviceToken(Base):
    """FCM/APNS device tokens for push notifications"""
    __tablename__ = "device_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Token Information
    token = Column(String(255), unique=True, nullable=False)
    device_type = Column(SQLEnum(DeviceType), nullable=False)
    device_name = Column(String(100), nullable=True)
    device_model = Column(String(50), nullable=True)
    os_version = Column(String(20), nullable=True)
    app_version = Column(String(20), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, default=func.now())
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Relationships
    user = relationship("User", backref="device_tokens")
    
    def __repr__(self):
        return f"<DeviceToken {self.device_type}: {self.token[:20]}...>"


class Notification(Base):
    """Notification history for users"""
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(String(50), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Notification Content
    title = Column(String(100), nullable=False)
    body = Column(Text, nullable=False)
    notification_type = Column(SQLEnum(NotificationType), nullable=False)
    priority = Column(SQLEnum(NotificationPriority), default=NotificationPriority.MEDIUM)
    
    # Additional Data
    data = Column(JSON, nullable=True)  # Extra payload (ride_id, etc.)
    image_url = Column(String(500), nullable=True)
    action_url = Column(String(500), nullable=True)  # Deep link
    
    # Status
    is_read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime, nullable=True)
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)
    is_delivered = Column(Boolean, default=False)
    delivered_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", backref="notifications")
    
    def __repr__(self):
        return f"<Notification {self.notification_type}: {self.title}>"


class NotificationPreference(Base):
    """User notification preferences"""
    __tablename__ = "notification_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # General Settings
    push_enabled = Column(Boolean, default=True)
    email_enabled = Column(Boolean, default=True)
    sms_enabled = Column(Boolean, default=False)
    
    # Quiet Hours
    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_hours_start = Column(String(5), default="22:00")  # Format: HH:MM
    quiet_hours_end = Column(String(5), default="07:00")
    
    # Specific Notification Types
    ride_updates = Column(Boolean, default=True)
    payment_updates = Column(Boolean, default=True)
    promotional = Column(Boolean, default=True)
    chat_messages = Column(Boolean, default=True)
    driver_nearby = Column(Boolean, default=True)
    earnings_updates = Column(Boolean, default=True)
    system_alerts = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Relationships
    user = relationship("User", backref="notification_preference", uselist=False)
    
    def __repr__(self):
        return f"<NotificationPreference for User {self.user_id}>"


class NotificationTemplate(Base):
    """Pre-defined notification templates"""
    __tablename__ = "notification_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    template_key = Column(String(50), unique=True, nullable=False)
    
    # Content
    title_template = Column(String(100), nullable=False)
    body_template = Column(Text, nullable=False)
    notification_type = Column(SQLEnum(NotificationType), nullable=False)
    default_priority = Column(SQLEnum(NotificationPriority), default=NotificationPriority.MEDIUM)
    
    # Defaults
    default_data = Column(JSON, nullable=True)
    default_image_url = Column(String(500), nullable=True)
    default_action_url = Column(String(500), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    def __repr__(self):
        return f"<NotificationTemplate {self.template_key}>"