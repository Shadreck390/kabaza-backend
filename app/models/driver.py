"""
Driver Model for Kabaza
Includes vehicle, earnings, and mobile money payout information
Optimized for TNM Mpamba & Airtel Money (Malawi)
"""

from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base
import enum


class DriverVerificationStatus(str, enum.Enum):
    """Driver verification status levels"""
    PENDING = "pending"
    DOCUMENTS_SUBMITTED = "documents_submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class DriverStatus(str, enum.Enum):
    """Driver availability status"""
    OFFLINE = "offline"
    ONLINE = "online"
    ON_RIDE = "on_ride"
    ON_BREAK = "on_break"


class VehicleType(str, enum.Enum):
    """Vehicle types available in Malawi"""
    MOTORCYCLE = "motorcycle"      # Kabaza (most common)
    BICYCLE = "bicycle"             # Kabaza ya njinga
    CAR = "car"                     # Standard taxi
    MINIBUS = "minibus"             # For groups
    TRUCK = "truck"                 # For deliveries


class PayoutMethod(str, enum.Enum):
    """Supported payout methods"""
    TNM_MPAMBA = "tnm_mpamba"
    AIRTEL_MONEY = "airtel_money"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"


class Driver(Base):
    """Driver profile model"""
    __tablename__ = "drivers"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Key to User
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Personal Information
    full_name = Column(String(100), nullable=False)
    national_id = Column(String(20), unique=True, nullable=True)  # Malawi National ID
    date_of_birth = Column(DateTime, nullable=True)
    
    # Contact Information
    phone = Column(String(20), unique=True, nullable=False, index=True)
    alternative_phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    
    # Address
    address = Column(String(255), nullable=True)
    city = Column(String(50), default="Lilongwe")
    district = Column(String(50), nullable=True)
    
    # Driver License
    license_number = Column(String(50), unique=True, nullable=True)
    license_expiry = Column(DateTime, nullable=True)
    license_front_image = Column(String(500), nullable=True)
    license_back_image = Column(String(500), nullable=True)
    
    # Profile Images
    profile_photo = Column(String(500), nullable=True)
    selfie_with_license = Column(String(500), nullable=True)
    
    # Verification
    verification_status = Column(
        SQLEnum(DriverVerificationStatus), 
        default=DriverVerificationStatus.PENDING
    )
    verification_notes = Column(Text, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Status
    status = Column(SQLEnum(DriverStatus), default=DriverStatus.OFFLINE)
    is_active = Column(Boolean, default=True)
    is_available_for_rides = Column(Boolean, default=False)
    
    # Ratings
    average_rating = Column(Float, default=0.0)
    total_ratings = Column(Integer, default=0)
    total_rides_completed = Column(Integer, default=0)
    total_rides_cancelled = Column(Integer, default=0)
    
    # Current Location (updated in real-time)
    current_latitude = Column(Float, nullable=True)
    current_longitude = Column(Float, nullable=True)
    location_updated_at = Column(DateTime, nullable=True)
    
    # Payout Information
    payout_method = Column(SQLEnum(PayoutMethod), default=PayoutMethod.TNM_MPAMBA)
    
    # TNM Mpamba Details
    tnm_mpamba_phone = Column(String(20), nullable=True)
    tnm_mpamba_registered_name = Column(String(100), nullable=True)
    
    # Airtel Money Details
    airtel_money_phone = Column(String(20), nullable=True)
    airtel_money_registered_name = Column(String(100), nullable=True)
    
    # Bank Details (for future)
    bank_name = Column(String(50), nullable=True)
    bank_account_number = Column(String(50), nullable=True)
    bank_account_name = Column(String(100), nullable=True)
    bank_branch = Column(String(50), nullable=True)
    
    # Earnings
    total_earnings = Column(Float, default=0.0)  # Total lifetime earnings
    available_balance = Column(Float, default=0.0)  # Available for payout
    pending_balance = Column(Float, default=0.0)   # Pending clearance
    total_paid_out = Column(Float, default=0.0)    # Total paid to driver
    
    # Commission (platform fee percentage)
    commission_rate = Column(Float, default=15.0)  # 15% platform fee
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_online_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="driver_profile")
    verifier = relationship("User", foreign_keys=[verified_by])
    vehicles = relationship("Vehicle", back_populates="driver", cascade="all, delete-orphan")
    documents = relationship("DriverDocument", back_populates="driver", cascade="all, delete-orphan")
    earnings_transactions = relationship("DriverEarning", back_populates="driver", cascade="all, delete-orphan")
    payouts = relationship("Payout", back_populates="driver", cascade="all, delete-orphan")
    rides = relationship("Ride", back_populates="driver")
    
    def __repr__(self):
        return f"<Driver {self.full_name} ({self.phone})>"
    
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
    def tnm_mpamba_full_number(self):
        """Get TNM Mpamba number in correct format"""
        if not self.tnm_mpamba_phone:
            return self.full_phone_number
        phone = self.tnm_mpamba_phone
        if phone.startswith('0'):
            return '+265' + phone[1:]
        elif not phone.startswith('+'):
            return '+265' + phone
        return phone
    
    @property
    def airtel_money_full_number(self):
        """Get Airtel Money number in correct format"""
        if not self.airtel_money_phone:
            return self.full_phone_number
        phone = self.airtel_money_phone
        if phone.startswith('0'):
            return '+265' + phone[1:]
        elif not phone.startswith('+'):
            return '+265' + phone
        return phone
    
    @property
    def is_tnm_number(self):
        """Check if phone is TNM (088, 098)"""
        phone = self.phone.replace('+265', '').replace(' ', '')
        return phone.startswith('088') or phone.startswith('098')
    
    @property
    def is_airtel_number(self):
        """Check if phone is Airtel (099, 088)"""
        phone = self.phone.replace('+265', '').replace(' ', '')
        return phone.startswith('099') or phone.startswith('088')
    
    @property
    def acceptance_rate(self):
        """Calculate ride acceptance rate"""
        if self.total_rides_completed + self.total_rides_cancelled == 0:
            return 0.0
        return (self.total_rides_completed / (self.total_rides_completed + self.total_rides_cancelled)) * 100


class Vehicle(Base):
    """Vehicle registered by driver"""
    __tablename__ = "vehicles"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    
    # Vehicle Information
    vehicle_type = Column(SQLEnum(VehicleType), nullable=False)
    make = Column(String(50), nullable=False)   # e.g., Honda, Toyota, Bajaj
    model = Column(String(50), nullable=False)  # e.g., CB125, Boxer
    year = Column(Integer, nullable=False)
    color = Column(String(30), nullable=False)
    
    # Registration
    registration_number = Column(String(20), unique=True, nullable=False)
    registration_expiry = Column(DateTime, nullable=True)
    
    # Insurance
    insurance_provider = Column(String(100), nullable=True)
    insurance_policy_number = Column(String(50), nullable=True)
    insurance_expiry = Column(DateTime, nullable=True)
    
    # COF (Certificate of Fitness - required in Malawi)
    cof_number = Column(String(50), nullable=True)
    cof_expiry = Column(DateTime, nullable=True)
    
    # Vehicle Images
    front_image = Column(String(500), nullable=True)
    back_image = Column(String(500), nullable=True)
    left_side_image = Column(String(500), nullable=True)
    right_side_image = Column(String(500), nullable=True)
    registration_image = Column(String(500), nullable=True)
    insurance_image = Column(String(500), nullable=True)
    
    # Verification
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # For motorcycles (Kabaza)
    has_helmet = Column(Boolean, default=False)
    has_reflective_jacket = Column(Boolean, default=False)
    max_passengers = Column(Integer, default=1)
    
    # For cars
    has_ac = Column(Boolean, default=False)
    max_luggage = Column(Integer, default=2)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    driver = relationship("Driver", back_populates="vehicles")
    
    def __repr__(self):
        return f"<Vehicle {self.make} {self.model} ({self.registration_number})>"


class DriverDocument(Base):
    """Additional documents for driver verification"""
    __tablename__ = "driver_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    
    document_type = Column(String(50), nullable=False)  # e.g., 'police_clearance', 'medical_certificate'
    document_number = Column(String(50), nullable=True)
    document_image = Column(String(500), nullable=False)
    expiry_date = Column(DateTime, nullable=True)
    
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verification_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    driver = relationship("Driver", back_populates="documents")
    verifier = relationship("User", foreign_keys=[verified_by])
    
    def __repr__(self):
        return f"<DriverDocument {self.document_type} for Driver {self.driver_id}>"


class DriverEarning(Base):
    """Individual earnings from completed rides"""
    __tablename__ = "driver_earnings"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    ride_id = Column(Integer, ForeignKey("rides.id"), nullable=False)
    
    # Amounts
    ride_fare = Column(Float, nullable=False)        # Total fare paid by rider
    platform_fee = Column(Float, nullable=False)     # Kabaza commission
    driver_earning = Column(Float, nullable=False)   # Amount driver receives
    tip_amount = Column(Float, default=0.0)          # Optional tip from rider
    
    # Status
    status = Column(String(20), default="pending")   # pending, cleared, paid_out
    cleared_at = Column(DateTime, nullable=True)
    paid_out_at = Column(DateTime, nullable=True)
    payout_id = Column(Integer, ForeignKey("payouts.id"), nullable=True)
    
    # Payment method used by rider
    rider_payment_method = Column(String(30), nullable=True)
    rider_payment_reference = Column(String(100), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    driver = relationship("Driver", back_populates="earnings_transactions")
    ride = relationship("Ride", foreign_keys=[ride_id])
    payout = relationship("Payout", foreign_keys=[payout_id])
    
    def __repr__(self):
        return f"<DriverEarning MK{self.driver_earning} from Ride {self.ride_id}>"


class Payout(Base):
    """Payout requests from drivers"""
    __tablename__ = "payouts"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=False)
    
    # Payout Details
    amount = Column(Float, nullable=False)
    fee = Column(Float, default=0.0)  # Payout processing fee
    net_amount = Column(Float, nullable=False)
    
    # Method
    payout_method = Column(SQLEnum(PayoutMethod), nullable=False)
    
    # TNM Mpamba Details
    tnm_mpamba_phone = Column(String(20), nullable=True)
    tnm_mpamba_transaction_id = Column(String(50), nullable=True)
    tnm_mpamba_status = Column(String(30), nullable=True)
    
    # Airtel Money Details
    airtel_money_phone = Column(String(20), nullable=True)
    airtel_money_transaction_id = Column(String(50), nullable=True)
    airtel_money_status = Column(String(30), nullable=True)
    
    # Bank Details
    bank_name = Column(String(50), nullable=True)
    bank_account_number = Column(String(50), nullable=True)
    bank_account_name = Column(String(100), nullable=True)
    bank_reference = Column(String(50), nullable=True)
    
    # Status
    status = Column(String(20), default="pending")  # pending, processing, completed, failed, cancelled
    processed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)
    
    # Reference
    reference_number = Column(String(50), unique=True, nullable=False)
    
    # Approval
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    driver = relationship("Driver", back_populates="payouts")
    requester = relationship("User", foreign_keys=[requested_by])
    approver = relationship("User", foreign_keys=[approved_by])
    earnings = relationship("DriverEarning", back_populates="payout")
    
    def __repr__(self):
        return f"<Payout MK{self.amount} to Driver {self.driver_id} via {self.payout_method}>"
    
    @property
    def mobile_money_phone(self):
        """Get phone number for mobile money payout"""
        if self.payout_method == PayoutMethod.TNM_MPAMBA:
            return self.tnm_mpamba_phone
        elif self.payout_method == PayoutMethod.AIRTEL_MONEY:
            return self.airtel_money_phone
        return None
    
    @property
    def mobile_money_transaction_id(self):
        """Get transaction ID for mobile money"""
        if self.payout_method == PayoutMethod.TNM_MPAMBA:
            return self.tnm_mpamba_transaction_id
        elif self.payout_method == PayoutMethod.AIRTEL_MONEY:
            return self.airtel_money_transaction_id
        return None