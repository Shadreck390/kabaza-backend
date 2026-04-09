"""
User Schemas for Kabaza
Includes request/response models for user authentication and profiles
Optimized for TNM Mpamba & Airtel Money (Malawi)
"""

from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ============================================
# ENUMS
# ============================================

class UserRoleEnum(str, Enum):
    """User role options"""
    RIDER = "rider"
    DRIVER = "driver"
    ADMIN = "admin"


class VerificationStatusEnum(str, Enum):
    """Verification status"""
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


# ============================================
# USER SCHEMAS
# ============================================

class UserBase(BaseModel):
    """Base user schema"""
    phone: str = Field(..., description="Phone number in +265 format")
    name: Optional[str] = Field(None, description="Full name")
    email: Optional[EmailStr] = Field(None, description="Email address")
    role: UserRoleEnum = Field(default=UserRoleEnum.RIDER, description="User role")
    
    @validator('phone')
    def format_phone(cls, v):
        """Format phone number to +265XXXXXXXXX"""
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if cleaned.startswith('0'):
            return '+265' + cleaned[1:]
        elif not cleaned.startswith('+'):
            return '+265' + cleaned
        return cleaned


class UserCreate(UserBase):
    """Schema for creating a new user"""
    password: Optional[str] = Field(None, description="Password (optional for OTP auth)")


class UserUpdate(BaseModel):
    """Schema for updating user"""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    profile_image: Optional[str] = None


class UserResponse(UserBase):
    """Schema for user response"""
    id: int
    is_verified: bool
    profile_image: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "phone": "+265999123456",
                "name": "Mary Phiri",
                "email": "mary@example.com",
                "role": "rider",
                "is_verified": True,
                "profile_image": "https://example.com/photo.jpg",
                "created_at": "2024-01-01T00:00:00Z"
            }
        }


class UserWithToken(BaseModel):
    """User response with auth tokens"""
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_profile_completion: bool = False


# ============================================
# AUTHENTICATION SCHEMAS
# ============================================

class PhoneLoginRequest(BaseModel):
    """Login with phone number"""
    phone: str = Field(..., description="Phone number")
    
    @validator('phone')
    def format_phone(cls, v):
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if cleaned.startswith('0'):
            return '+265' + cleaned[1:]
        elif not cleaned.startswith('+'):
            return '+265' + cleaned
        return cleaned


class OTPVerifyRequest(BaseModel):
    """Verify OTP"""
    phone: str
    otp: str
    role: Optional[str] = "rider"
    name: Optional[str] = ""
    
    @validator('phone')
    def format_phone(cls, v):
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if cleaned.startswith('0'):
            return '+265' + cleaned[1:]
        elif not cleaned.startswith('+'):
            return '+265' + cleaned
        return cleaned
    
    @validator('otp')
    def validate_otp(cls, v):
        if len(v) != 6 or not v.isdigit():
            raise ValueError('OTP must be 6 digits')
        return v


class OTPResponse(BaseModel):
    """OTP send response"""
    success: bool
    message: str
    expires_in: int = 300
    debug_otp: Optional[str] = None


# ============================================
# PROFILE SCHEMAS
# ============================================

class ProfileCompletionRequest(BaseModel):
    """Complete user profile"""
    name: str = Field(..., min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    date_of_birth: Optional[datetime] = None
    gender: Optional[str] = Field(None, pattern="^(M|F|Other)$")
    profile_image: Optional[str] = None


class ProfileResponse(BaseModel):
    """Complete profile response"""
    id: int
    phone: str
    name: str
    email: Optional[str] = None
    role: str
    is_verified: bool
    profile_image: Optional[str] = None
    average_rating: Optional[float] = None
    total_rides: Optional[int] = None
    wallet_balance: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============================================
# RIDER PROFILE SCHEMAS
# ============================================

class RiderProfileResponse(BaseModel):
    """Rider profile response"""
    id: int
    user_id: int
    full_name: str
    phone: str
    email: Optional[str] = None
    profile_photo: Optional[str] = None
    status: str
    average_rating: float
    total_ratings: int
    total_rides_taken: int
    wallet_balance: float
    total_spent: float
    default_payment_method: str
    referral_code: Optional[str] = None
    referral_credits: float
    created_at: datetime
    last_ride_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class RiderProfileUpdate(BaseModel):
    """Update rider profile"""
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    profile_photo: Optional[str] = None
    default_payment_method: Optional[str] = None
    preferred_vehicle_type: Optional[str] = None


# ============================================
# DRIVER PROFILE SCHEMAS
# ============================================

class DriverProfileResponse(BaseModel):
    """Driver profile response"""
    id: int
    driver_id: Optional[str] = None
    user_id: Optional[int] = None
    full_name: str
    phone: str
    alternative_phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    profile_photo: Optional[str] = None
    verification_status: str
    driver_status: str
    is_available_for_rides: bool
    average_rating: float
    total_ratings: int
    total_rides_completed: int
    
    # Payout Information
    payout_method: str
    tnm_mpamba_phone: Optional[str] = None
    airtel_money_phone: Optional[str] = None
    
    # Earnings
    total_earnings: float
    available_balance: float
    pending_balance: float
    total_paid_out: float
    
    # Documents
    license_verified: bool
    vehicle_verified: bool
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class DriverProfileUpdate(BaseModel):
    """Update driver profile"""
    full_name: Optional[str] = None
    alternative_phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    profile_photo: Optional[str] = None
    payout_method: Optional[str] = None
    tnm_mpamba_phone: Optional[str] = None
    airtel_money_phone: Optional[str] = None
    
    @validator('tnm_mpamba_phone', 'airtel_money_phone')
    def format_phone(cls, v):
        if not v:
            return v
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if cleaned.startswith('0'):
            return '+265' + cleaned[1:]
        elif not cleaned.startswith('+'):
            return '+265' + cleaned
        return v


class DriverVerificationRequest(BaseModel):
    """Submit driver verification documents"""
    national_id: str
    license_number: str
    license_expiry: datetime
    license_front_image: str
    license_back_image: Optional[str] = None
    profile_photo: str
    selfie_with_license: str


class VehicleRegistrationRequest(BaseModel):
    """Register a vehicle"""
    vehicle_type: str
    make: str
    model: str
    year: int
    color: str
    registration_number: str
    front_image: str
    back_image: Optional[str] = None
    has_helmet: bool = False
    has_reflective_jacket: bool = False


# ============================================
# WALLET SCHEMAS
# ============================================

class WalletTransactionResponse(BaseModel):
    """Wallet transaction response"""
    id: int
    transaction_type: str
    amount: float
    balance_before: float
    balance_after: float
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    description: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class WalletTopupRequest(BaseModel):
    """Top up wallet via mobile money"""
    amount: float = Field(..., gt=0, le=100000, description="Amount in MWK")
    payment_method: str = Field(..., pattern="^(tnm_mpamba|airtel_money)$")
    phone_number: str
    
    @validator('phone_number')
    def format_phone(cls, v):
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if cleaned.startswith('0'):
            return '+265' + cleaned[1:]
        elif not cleaned.startswith('+'):
            return '+265' + cleaned
        return v


class WalletBalanceResponse(BaseModel):
    """Wallet balance response"""
    balance: float
    currency: str = "MWK"
    total_spent: float
    total_saved: float
    referral_credits: float


# ============================================
# FAVORITE LOCATION SCHEMAS
# ============================================

class FavoriteLocationCreate(BaseModel):
    """Create favorite location"""
    name: str = Field(..., min_length=1, max_length=50)
    address: str
    latitude: float
    longitude: float
    place_id: Optional[str] = None
    icon: Optional[str] = None


class FavoriteLocationResponse(BaseModel):
    """Favorite location response"""
    id: int
    name: str
    address: str
    latitude: float
    longitude: float
    place_id: Optional[str] = None
    icon: Optional[str] = None
    visit_count: int
    created_at: datetime
    last_used_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ============================================
# PAYMENT METHOD SCHEMAS
# ============================================

class PaymentMethodCreate(BaseModel):
    """Add payment method"""
    method_type: str = Field(..., pattern="^(tnm_mpamba|airtel_money|card)$")
    phone: Optional[str] = None
    nickname: Optional[str] = None
    is_default: bool = False
    
    @validator('phone')
    def format_phone(cls, v):
        if not v:
            return v
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if cleaned.startswith('0'):
            return '+265' + cleaned[1:]
        elif not cleaned.startswith('+'):
            return '+265' + cleaned
        return v


class PaymentMethodResponse(BaseModel):
    """Payment method response"""
    id: int
    method_type: str
    display_name: str
    phone_number: Optional[str] = None
    is_default: bool
    is_verified: bool
    last_used_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True