"""
Rider Model for Kabaza
Includes favorite locations, payment methods, and ride history
Optimized for TNM Mpamba & Airtel Money payments (Malawi)
"""

from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base
import enum


class RiderStatus(str, enum.Enum):
    """Rider account status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"


class PaymentMethodType(str, enum.Enum):
    """Supported payment methods for riders"""
    CASH = "cash"
    TNM_MPAMBA = "tnm_mpamba"
    AIRTEL_MONEY = "airtel_money"
    CARD = "card"  # For future
    WALLET = "wallet"  # In-app wallet balance


class Rider(Base):
    """Rider profile model"""
    __tablename__ = "riders"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Key to User
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Personal Information
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(100), nullable=True)
    
    # Profile
    profile_photo = Column(String(500), nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    gender = Column(String(10), nullable=True)  # M, F, Other
    
    # Status
    status = Column(SQLEnum(RiderStatus), default=RiderStatus.ACTIVE)
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    
    # Ratings
    average_rating = Column(Float, default=5.0)
    total_ratings = Column(Integer, default=0)
    total_rides_taken = Column(Integer, default=0)
    total_rides_cancelled = Column(Integer, default=0)
    
    # Wallet (in-app balance)
    wallet_balance = Column(Float, default=0.0)
    total_spent = Column(Float, default=0.0)
    total_saved = Column(Float, default=0.0)  # From discounts/promos
    
    # Default Preferences
    default_payment_method = Column(SQLEnum(PaymentMethodType), default=PaymentMethodType.CASH)
    preferred_vehicle_type = Column(String(20), default="motorcycle")
    
    # Referral
    referral_code = Column(String(20), unique=True, nullable=True)
    referred_by = Column(String(20), nullable=True)
    referral_credits = Column(Float, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_ride_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="rider_profile")
    favorite_locations = relationship("FavoriteLocation", back_populates="rider", cascade="all, delete-orphan")
    payment_methods = relationship("RiderPaymentMethod", back_populates="rider", cascade="all, delete-orphan")
    wallet_transactions = relationship("WalletTransaction", back_populates="rider", cascade="all, delete-orphan")
    rides = relationship("Ride", back_populates="rider")
    
    def __repr__(self):
        return f"<Rider {self.full_name} ({self.phone})>"
    
    @property
    def full_phone_number(self):
        """Ensure phone is in +265 format"""
        phone = self.phone
        if phone.startswith('0'):
            return '+265' + phone[1:]
        elif not phone.startswith('+'):
            return '+265' + phone
        return phone
    
    @property
    def cancellation_rate(self):
        """Calculate ride cancellation rate"""
        if self.total_rides_taken + self.total_rides_cancelled == 0:
            return 0.0
        return (self.total_rides_cancelled / (self.total_rides_taken + self.total_rides_cancelled)) * 100


class FavoriteLocation(Base):
    """Saved locations for quick booking"""
    __tablename__ = "favorite_locations"
    
    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=False)
    
    # Location Details
    name = Column(String(50), nullable=False)  # e.g., "Home", "Work", "Gym"
    address = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    
    # Additional Info
    place_id = Column(String(100), nullable=True)  # Google Places ID
    icon = Column(String(50), nullable=True)  # Emoji or icon name
    is_frequent = Column(Boolean, default=False)
    visit_count = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime, nullable=True)
    
    # Relationships
    rider = relationship("Rider", back_populates="favorite_locations")
    
    def __repr__(self):
        return f"<FavoriteLocation {self.name} for Rider {self.rider_id}>"


class RiderPaymentMethod(Base):
    """Saved payment methods for riders"""
    __tablename__ = "rider_payment_methods"
    
    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=False)
    
    # Payment Method Details
    method_type = Column(SQLEnum(PaymentMethodType), nullable=False)
    is_default = Column(Boolean, default=False)
    
    # TNM Mpamba
    tnm_mpamba_phone = Column(String(20), nullable=True)
    tnm_mpamba_nickname = Column(String(50), nullable=True)  # e.g., "My TNM"
    
    # Airtel Money
    airtel_money_phone = Column(String(20), nullable=True)
    airtel_money_nickname = Column(String(50), nullable=True)  # e.g., "My Airtel"
    
    # Card (for future)
    card_last4 = Column(String(4), nullable=True)
    card_brand = Column(String(20), nullable=True)  # Visa, Mastercard
    card_expiry_month = Column(Integer, nullable=True)
    card_expiry_year = Column(Integer, nullable=True)
    card_token = Column(String(200), nullable=True)  # Token from payment gateway
    
    # Status
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    rider = relationship("Rider", back_populates="payment_methods")
    
    def __repr__(self):
        return f"<RiderPaymentMethod {self.method_type} for Rider {self.rider_id}>"
    
    @property
    def display_name(self):
        """Get display name for payment method"""
        if self.method_type == PaymentMethodType.TNM_MPAMBA:
            return self.tnm_mpamba_nickname or f"TNM Mpamba (***{self.tnm_mpamba_phone[-4:] if self.tnm_mpamba_phone else ''})"
        elif self.method_type == PaymentMethodType.AIRTEL_MONEY:
            return self.airtel_money_nickname or f"Airtel Money (***{self.airtel_money_phone[-4:] if self.airtel_money_phone else ''})"
        elif self.method_type == PaymentMethodType.CASH:
            return "Cash"
        elif self.method_type == PaymentMethodType.WALLET:
            return "Kabaza Wallet"
        elif self.method_type == PaymentMethodType.CARD:
            return f"{self.card_brand} ****{self.card_last4}"
        return str(self.method_type)
    
    @property
    def phone_number(self):
        """Get phone number for mobile money"""
        if self.method_type == PaymentMethodType.TNM_MPAMBA:
            phone = self.tnm_mpamba_phone
        elif self.method_type == PaymentMethodType.AIRTEL_MONEY:
            phone = self.airtel_money_phone
        else:
            return None
        
        if phone and phone.startswith('0'):
            return '+265' + phone[1:]
        elif phone and not phone.startswith('+'):
            return '+265' + phone
        return phone


class WalletTransaction(Base):
    """Rider wallet transactions"""
    __tablename__ = "wallet_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=False)
    
    # Transaction Details
    transaction_type = Column(String(20), nullable=False)  # deposit, withdrawal, payment, refund, referral_credit
    amount = Column(Float, nullable=False)
    balance_before = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    
    # Payment Method Used
    payment_method = Column(String(30), nullable=True)
    payment_reference = Column(String(100), nullable=True)
    
    # TNM Mpamba Details
    tnm_mpamba_transaction_id = Column(String(50), nullable=True)
    tnm_mpamba_status = Column(String(30), nullable=True)
    
    # Airtel Money Details
    airtel_money_transaction_id = Column(String(50), nullable=True)
    airtel_money_status = Column(String(30), nullable=True)
    
    # Reference
    reference_type = Column(String(30), nullable=True)  # ride, topup, refund, referral
    reference_id = Column(Integer, nullable=True)       # ID of related record
    description = Column(String(255), nullable=True)
    
    # Status
    status = Column(String(20), default="pending")  # pending, completed, failed, cancelled
    completed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    rider = relationship("Rider", back_populates="wallet_transactions")
    
    def __repr__(self):
        return f"<WalletTransaction {self.transaction_type} MK{self.amount} for Rider {self.rider_id}>"


class RiderPromo(Base):
    """Promo codes used by riders"""
    __tablename__ = "rider_promos"
    
    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=False)
    
    promo_code = Column(String(50), nullable=False)
    discount_type = Column(String(20), nullable=False)  # percentage, fixed
    discount_value = Column(Float, nullable=False)
    max_discount = Column(Float, nullable=True)
    
    ride_id = Column(Integer, ForeignKey("rides.id"), nullable=True)
    discount_applied = Column(Float, default=0.0)
    
    used_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime, nullable=True)
    
    # Relationships
    rider = relationship("Rider", foreign_keys=[rider_id])
    ride = relationship("Ride", foreign_keys=[ride_id])
    
    def __repr__(self):
        return f"<RiderPromo {self.promo_code} for Rider {self.rider_id}>"