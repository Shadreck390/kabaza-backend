"""
Unified SQL Models for Kabaza
Combines all models with proper relationships
Compatible with existing ride structure
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Numeric, Boolean, JSON, ForeignKey, Text, Enum, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

Base = declarative_base()


# ============================================
# ENUMS
# ============================================

class RideStatus(str, enum.Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED_BY_RIDER = "cancelled_by_rider"
    CANCELLED_BY_DRIVER = "cancelled_by_driver"


class PaymentStatus(str, enum.Enum):
    """Payment status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PayoutMethod(str, enum.Enum):
    """Payout method enum for mobile money"""
    TNM_MPAMBA = "tnm_mpamba"
    AIRTEL_MONEY = "airtel_money"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"


class VehicleType(str, enum.Enum):
    """Vehicle types"""
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    CAR = "car"
    MINIBUS = "minibus"
    TRUCK = "truck"


# ============================================
# USER MODEL (Extended)
# ============================================

class User(Base):
    """User model - compatible with existing structure"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=True)
    email = Column(String(100), nullable=True)
    password = Column(String(255), nullable=True)  # Hashed password for email login
    role = Column(String(20), default="rider")  # rider, driver, admin
    is_verified = Column(Boolean, default=False)
    profile_image = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Relationships
    driver_profile = relationship("Driver", back_populates="user", uselist=False, cascade="all, delete-orphan")
    rider_profile = relationship("Rider", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.phone} ({self.role})>"


# ============================================
# DRIVER MODEL (Extended - Compatible)
# ============================================

class Driver(Base):
    """Driver model - extended with mobile money support"""
    __tablename__ = "drivers"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(String(50), unique=True, index=True, nullable=True)  # For compatibility
    
    # Foreign Key to User
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)
    
    # Personal Information
    full_name = Column(String(100), nullable=True)
    national_id = Column(String(20), unique=True, nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    
    # Contact
    phone = Column(String(20), unique=True, nullable=True, index=True)
    alternative_phone = Column(String(20), nullable=True)
    
    # Address
    address = Column(String(255), nullable=True)
    city = Column(String(50), default="Lilongwe")
    
    # License
    license_number = Column(String(50), unique=True, nullable=True)
    license_expiry = Column(DateTime, nullable=True)
    license_front_image = Column(String(500), nullable=True)
    license_back_image = Column(String(500), nullable=True)
    
    # Profile
    profile_photo = Column(String(500), nullable=True)
    
    # Verification
    verification_status = Column(String(30), default="pending")
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    
    # Status (compatible with existing)
    driver_status = Column(String(20), default="offline")  # offline, online, on_ride, on_break
    last_status_update = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Location
    current_location = Column(JSON, nullable=True)
    last_location = Column(JSON, nullable=True)
    last_active = Column(DateTime, default=datetime.utcnow)
    
    # Ratings
    average_rating = Column(Float, default=0.0)
    total_ratings = Column(Integer, default=0)
    total_rides_completed = Column(Integer, default=0)
    total_rides_cancelled = Column(Integer, default=0)
    
    # ============================================
    # MOBILE MONEY PAYOUT DETAILS
    # ============================================
    payout_method = Column(SQLEnum(PayoutMethod), default=PayoutMethod.TNM_MPAMBA)
    
    # TNM Mpamba
    tnm_mpamba_phone = Column(String(20), nullable=True)
    tnm_mpamba_registered_name = Column(String(100), nullable=True)
    
    # Airtel Money
    airtel_money_phone = Column(String(20), nullable=True)
    airtel_money_registered_name = Column(String(100), nullable=True)
    
    # Bank Details (future)
    bank_name = Column(String(50), nullable=True)
    bank_account_number = Column(String(50), nullable=True)
    bank_account_name = Column(String(100), nullable=True)
    bank_branch = Column(String(50), nullable=True)
    
    # Earnings
    total_earnings = Column(Float, default=0.0)
    available_balance = Column(Float, default=0.0)
    pending_balance = Column(Float, default=0.0)
    total_paid_out = Column(Float, default=0.0)
    commission_rate = Column(Float, default=15.0)  # 15% platform fee
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="driver_profile", foreign_keys=[user_id])
    vehicles = relationship("Vehicle", back_populates="driver", cascade="all, delete-orphan")
    payouts = relationship("Payout", back_populates="driver", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Driver {self.full_name or self.phone}>"
    
    @property
    def full_phone_number(self):
        """Ensure phone is in +265 format for mobile money"""
        phone = self.phone or (self.user.phone if self.user else None)
        if not phone:
            return None
        if phone.startswith('0'):
            return '+265' + phone[1:]
        elif not phone.startswith('+'):
            return '+265' + phone
        return phone
    
    @property
    def tnm_mpamba_full_number(self):
        """Get TNM Mpamba number in correct format"""
        phone = self.tnm_mpamba_phone or self.full_phone_number
        if not phone:
            return None
        if phone.startswith('0'):
            return '+265' + phone[1:]
        elif not phone.startswith('+'):
            return '+265' + phone
        return phone
    
    @property
    def airtel_money_full_number(self):
        """Get Airtel Money number in correct format"""
        phone = self.airtel_money_phone or self.full_phone_number
        if not phone:
            return None
        if phone.startswith('0'):
            return '+265' + phone[1:]
        elif not phone.startswith('+'):
            return '+265' + phone
        return phone


# ============================================
# RIDER MODEL (New - Compatible)
# ============================================

class Rider(Base):
    """Rider model with mobile money payment support"""
    __tablename__ = "riders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Personal Information
    full_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True, index=True)
    email = Column(String(100), nullable=True)
    
    # Profile
    profile_photo = Column(String(500), nullable=True)
    
    # Status
    status = Column(String(20), default="active")
    is_verified = Column(Boolean, default=False)
    
    # Ratings
    average_rating = Column(Float, default=5.0)
    total_ratings = Column(Integer, default=0)
    total_rides_taken = Column(Integer, default=0)
    total_rides_cancelled = Column(Integer, default=0)
    
    # Wallet (in-app balance)
    wallet_balance = Column(Float, default=0.0)
    total_spent = Column(Float, default=0.0)
    
    # Default Preferences
    default_payment_method = Column(String(30), default="cash")
    preferred_vehicle_type = Column(String(20), default="motorcycle")
    
    # Referral
    referral_code = Column(String(20), unique=True, nullable=True)
    referred_by = Column(String(20), nullable=True)
    referral_credits = Column(Float, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_ride_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="rider_profile", foreign_keys=[user_id])
    favorite_locations = relationship("FavoriteLocation", back_populates="rider", cascade="all, delete-orphan")
    payment_methods = relationship("RiderPaymentMethod", back_populates="rider", cascade="all, delete-orphan")
    wallet_transactions = relationship("WalletTransaction", back_populates="rider", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Rider {self.full_name or self.phone}>"


# ============================================
# RIDE MODEL (Extended - Compatible)
# ============================================

class Ride(Base):
    __tablename__ = "rides"

    id = Column(Integer, primary_key=True, index=True)
    ride_id = Column(String(50), unique=True, nullable=False)
    rider_id = Column(Integer, index=True)
    rider_name = Column(String(100))
    driver_id = Column(Integer, index=True, nullable=True)
    driver_name = Column(String(100), nullable=True)
    pickup_location = Column(JSONB, nullable=False)
    destination = Column(JSONB, nullable=False)
    waypoints = Column(JSONB, default=list)
    payment_method = Column(String(20), default="cash")
    status = Column(String(30), default="requested")
    fare = Column(Numeric(10, 2), default=0)
    distance_km = Column(Numeric(10, 2), default=0)
    duration_minutes = Column(Integer, default=0)
    requested_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String, nullable=True)
    is_scheduled = Column(Boolean, default=False)
    scheduled_for = Column(DateTime(timezone=True), nullable=True)


# ============================================
# VEHICLE MODEL
# ============================================

class Vehicle(Base):
    """Vehicle registered by driver"""
    __tablename__ = "vehicles"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    
    vehicle_type = Column(SQLEnum(VehicleType), nullable=False)
    make = Column(String(50), nullable=False)
    model = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False)
    color = Column(String(30), nullable=False)
    registration_number = Column(String(20), unique=True, nullable=False)
    
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Images
    front_image = Column(String(500), nullable=True)
    back_image = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    driver = relationship("Driver", back_populates="vehicles")
    
    def __repr__(self):
        return f"<Vehicle {self.make} {self.model} ({self.registration_number})>"


# ============================================
# DRIVER EARNING MODEL
# ============================================

class DriverEarning(Base):
    """Individual earnings from completed rides"""
    __tablename__ = "driver_earnings"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    ride_id = Column(Integer, ForeignKey("rides.id"), nullable=False)
    
    ride_fare = Column(Float, nullable=False)
    platform_fee = Column(Float, nullable=False)
    driver_earning = Column(Float, nullable=False)
    tip_amount = Column(Float, default=0.0)
    
    status = Column(String(20), default="pending")  # pending, cleared, paid_out
    cleared_at = Column(DateTime, nullable=True)
    paid_out_at = Column(DateTime, nullable=True)
    payout_id = Column(Integer, ForeignKey("payouts.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    driver = relationship("Driver", foreign_keys=[driver_id])
    payout = relationship("Payout", foreign_keys=[payout_id])


# ============================================
# PAYOUT MODEL (Mobile Money)
# ============================================

class Payout(Base):
    """Payout requests from drivers"""
    __tablename__ = "payouts"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    
    amount = Column(Float, nullable=False)
    fee = Column(Float, default=0.0)
    net_amount = Column(Float, nullable=False)
    
    payout_method = Column(SQLEnum(PayoutMethod), nullable=False)
    
    # TNM Mpamba
    tnm_mpamba_phone = Column(String(20), nullable=True)
    tnm_mpamba_transaction_id = Column(String(50), nullable=True)
    tnm_mpamba_status = Column(String(30), nullable=True)
    
    # Airtel Money
    airtel_money_phone = Column(String(20), nullable=True)
    airtel_money_transaction_id = Column(String(50), nullable=True)
    airtel_money_status = Column(String(30), nullable=True)
    
    status = Column(String(20), default="pending")
    reference_number = Column(String(50), unique=True, nullable=False)
    
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    driver = relationship("Driver", back_populates="payouts", foreign_keys=[driver_id])


# ============================================
# RIDER PAYMENT METHOD MODEL
# ============================================

class RiderPaymentMethod(Base):
    """Saved payment methods for riders"""
    __tablename__ = "rider_payment_methods"
    
    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=False)
    
    method_type = Column(String(30), nullable=False)  # cash, tnm_mpamba, airtel_money, card, wallet
    is_default = Column(Boolean, default=False)
    
    # TNM Mpamba
    tnm_mpamba_phone = Column(String(20), nullable=True)
    tnm_mpamba_nickname = Column(String(50), nullable=True)
    
    # Airtel Money
    airtel_money_phone = Column(String(20), nullable=True)
    airtel_money_nickname = Column(String(50), nullable=True)
    
    is_verified = Column(Boolean, default=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    rider = relationship("Rider", back_populates="payment_methods", foreign_keys=[rider_id])


# ============================================
# FAVORITE LOCATION MODEL
# ============================================

class FavoriteLocation(Base):
    """Saved locations for quick booking"""
    __tablename__ = "favorite_locations"
    
    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=False)
    
    name = Column(String(50), nullable=False)
    address = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    
    place_id = Column(String(100), nullable=True)
    icon = Column(String(50), nullable=True)
    visit_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    
    # Relationships
    rider = relationship("Rider", back_populates="favorite_locations", foreign_keys=[rider_id])


# ============================================
# WALLET TRANSACTION MODEL
# ============================================

class WalletTransaction(Base):
    """Rider wallet transactions"""
    __tablename__ = "wallet_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("riders.id"), nullable=False)
    
    transaction_type = Column(String(20), nullable=False)  # deposit, withdrawal, payment, refund
    amount = Column(Float, nullable=False)
    balance_before = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    
    payment_method = Column(String(30), nullable=True)
    payment_reference = Column(String(100), nullable=True)
    
    # Mobile Money specific
    tnm_mpamba_transaction_id = Column(String(50), nullable=True)
    airtel_money_transaction_id = Column(String(50), nullable=True)
    
    reference_type = Column(String(30), nullable=True)  # ride, topup, refund
    reference_id = Column(Integer, nullable=True)
    description = Column(String(255), nullable=True)
    
    status = Column(String(20), default="pending")
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    rider = relationship("Rider", back_populates="wallet_transactions", foreign_keys=[rider_id])


# ============================================
# OTP MODEL
# ============================================

class OTP(Base):
    """OTP storage for verification"""
    __tablename__ = "otps"
    
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), index=True, nullable=False)
    code = Column(String(10), nullable=False)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)