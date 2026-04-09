"""
Ride Schemas for Kabaza
Includes request/response models for rides with mobile money payment support
Optimized for TNM Mpamba & Airtel Money (Malawi)
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ============================================
# ENUMS
# ============================================

class RideStatusEnum(str, Enum):
    """Ride status options"""
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    DRIVER_ARRIVED = "driver_arrived"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED_BY_RIDER = "cancelled_by_rider"
    CANCELLED_BY_DRIVER = "cancelled_by_driver"


class PaymentMethodEnum(str, Enum):
    """Payment method options for riders"""
    CASH = "cash"
    TNM_MPAMBA = "tnm_mpamba"
    AIRTEL_MONEY = "airtel_money"
    WALLET = "wallet"
    CARD = "card"


class PaymentStatusEnum(str, Enum):
    """Payment status options"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class VehicleTypeEnum(str, Enum):
    """Vehicle type options"""
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    CAR = "car"
    MINIBUS = "minibus"
    TRUCK = "truck"


# ============================================
# LOCATION SCHEMAS
# ============================================

class Location(BaseModel):
    """Location with coordinates and address"""
    latitude: float = Field(..., description="Latitude coordinate")
    longitude: float = Field(..., description="Longitude coordinate")
    address: str = Field(..., description="Human-readable address")
    name: Optional[str] = Field(None, description="Place name (e.g., 'Lilongwe City Mall')")
    place_id: Optional[str] = Field(None, description="Google Places ID")
    
    @validator('latitude')
    def validate_latitude(cls, v):
        if v < -90 or v > 90:
            raise ValueError('Latitude must be between -90 and 90')
        return v
    
    @validator('longitude')
    def validate_longitude(cls, v):
        if v < -180 or v > 180:
            raise ValueError('Longitude must be between -180 and 180')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "latitude": -13.9626,
                "longitude": 33.7741,
                "address": "Area 3, Lilongwe",
                "name": "Lilongwe City Centre"
            }
        }


class LocationUpdate(BaseModel):
    """Real-time location update"""
    latitude: float
    longitude: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    bearing: Optional[float] = Field(None, description="Direction in degrees")
    speed: Optional[float] = Field(None, description="Speed in km/h")
    accuracy: Optional[float] = Field(None, description="GPS accuracy in meters")


# ============================================
# RIDE REQUEST SCHEMAS
# ============================================

class RideRequest(BaseModel):
    """Request a new ride"""
    pickup_location: Location = Field(..., description="Pickup location details")
    destination: Location = Field(..., description="Drop-off location details")
    waypoints: Optional[List[Location]] = Field(None, description="Optional stops along the way")
    
    vehicle_type: VehicleTypeEnum = Field(
        default=VehicleTypeEnum.MOTORCYCLE,
        description="Type of vehicle requested"
    )
    
    payment_method: PaymentMethodEnum = Field(
        default=PaymentMethodEnum.CASH,
        description="Payment method for this ride"
    )
    
    # Mobile Money specific fields
    payment_phone: Optional[str] = Field(
        None, 
        description="Phone number for mobile money payment"
    )
    
    # Scheduled ride
    is_scheduled: bool = Field(False, description="Whether this is a scheduled ride")
    scheduled_for: Optional[datetime] = Field(None, description="Scheduled pickup time")
    
    # Optional preferences
    note_for_driver: Optional[str] = Field(None, description="Special instructions for driver")
    promo_code: Optional[str] = Field(None, description="Promo code for discount")
    
    @validator('payment_phone')
    def validate_payment_phone(cls, v, values):
        """Ensure payment phone is provided for mobile money payments"""
        payment_method = values.get('payment_method')
        if payment_method in [PaymentMethodEnum.TNM_MPAMBA, PaymentMethodEnum.AIRTEL_MONEY]:
            if not v:
                raise ValueError(f'Payment phone number is required for {payment_method}')
        return v
    
    @validator('payment_phone')
    def format_phone(cls, v):
        """Format phone number to +265XXXXXXXXX"""
        if not v:
            return v
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if cleaned.startswith('0'):
            return '+265' + cleaned[1:]
        elif not cleaned.startswith('+'):
            return '+265' + cleaned
        return cleaned
    
    @validator('scheduled_for')
    def validate_scheduled_time(cls, v, values):
        """Ensure scheduled time is in the future"""
        if values.get('is_scheduled') and v:
            if v < datetime.utcnow():
                raise ValueError('Scheduled time must be in the future')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "pickup_location": {
                    "latitude": -13.9626,
                    "longitude": 33.7741,
                    "address": "Area 3, Lilongwe"
                },
                "destination": {
                    "latitude": -13.9833,
                    "longitude": 33.7833,
                    "address": "City Centre, Lilongwe"
                },
                "vehicle_type": "motorcycle",
                "payment_method": "tnm_mpamba",
                "payment_phone": "0888123456"
            }
        }


class RideEstimateRequest(BaseModel):
    """Request fare estimate before booking"""
    pickup_location: Location
    destination: Location
    vehicle_type: VehicleTypeEnum = VehicleTypeEnum.MOTORCYCLE
    
    class Config:
        json_schema_extra = {
            "example": {
                "pickup_location": {
                    "latitude": -13.9626,
                    "longitude": 33.7741,
                    "address": "Area 3, Lilongwe"
                },
                "destination": {
                    "latitude": -13.9833,
                    "longitude": 33.7833,
                    "address": "City Centre, Lilongwe"
                },
                "vehicle_type": "motorcycle"
            }
        }


# ============================================
# RIDE RESPONSE SCHEMAS
# ============================================

class RideEstimateResponse(BaseModel):
    """Fare estimate response"""
    distance_km: float = Field(..., description="Estimated distance in kilometers")
    duration_minutes: int = Field(..., description="Estimated duration in minutes")
    base_fare: float = Field(..., description="Base fare before fees")
    platform_fee: float = Field(..., description="Kabaza platform fee")
    total_fare: float = Field(..., description="Total estimated fare")
    currency: str = Field(default="MWK", description="Currency code")
    
    class Config:
        json_schema_extra = {
            "example": {
                "distance_km": 5.2,
                "duration_minutes": 15,
                "base_fare": 1500.0,
                "platform_fee": 225.0,
                "total_fare": 1725.0,
                "currency": "MWK"
            }
        }


class DriverInfo(BaseModel):
    """Driver information in ride response"""
    id: int
    driver_id: str
    name: str
    phone: str
    rating: Optional[float] = None
    profile_photo: Optional[str] = None
    vehicle: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "driver_id": "DRV-001",
                "name": "John Banda",
                "phone": "+265888123456",
                "rating": 4.8,
                "profile_photo": "https://example.com/photo.jpg",
                "vehicle": {
                    "make": "Honda",
                    "model": "CB125",
                    "color": "Red",
                    "registration": "MZ 1234"
                }
            }
        }


class RiderInfo(BaseModel):
    """Rider information in ride response"""
    id: int
    name: str
    phone: str
    rating: Optional[float] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "Mary Phiri",
                "phone": "+265999123456",
                "rating": 4.5
            }
        }


class PaymentInfo(BaseModel):
    """Payment information in ride response"""
    method: PaymentMethodEnum
    status: PaymentStatusEnum
    amount: float
    platform_fee: float
    driver_earning: float
    tip: Optional[float] = 0.0
    
    # Mobile Money specific
    provider: Optional[str] = Field(None, description="tnm_mpamba or airtel_money")
    transaction_id: Optional[str] = None
    phone: Optional[str] = None
    completed_at: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "method": "tnm_mpamba",
                "status": "completed",
                "amount": 1725.0,
                "platform_fee": 225.0,
                "driver_earning": 1500.0,
                "tip": 100.0,
                "provider": "tnm_mpamba",
                "transaction_id": "MPAMBA-2024-001234",
                "phone": "+265888123456"
            }
        }


class RideResponse(BaseModel):
    """Complete ride response"""
    id: int
    ride_id: str
    status: RideStatusEnum
    
    # Participants
    rider: RiderInfo
    driver: Optional[DriverInfo] = None
    
    # Locations
    pickup_location: Location
    destination: Location
    waypoints: Optional[List[Location]] = None
    
    # Ride Details
    distance_km: float
    duration_minutes: int
    fare: float
    
    # Payment
    payment: PaymentInfo
    
    # Timestamps
    requested_at: datetime
    accepted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    
    # Driver Location (real-time)
    driver_location: Optional[LocationUpdate] = None
    
    # Scheduled
    is_scheduled: bool = False
    scheduled_for: Optional[datetime] = None
    
    # Rating
    rating: Optional[int] = None
    rating_comment: Optional[str] = None
    
    # Cancellation
    cancellation_reason: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 100,
                "ride_id": "RIDE-2024-00100",
                "status": "completed",
                "rider": {
                    "id": 1,
                    "name": "Mary Phiri",
                    "phone": "+265999123456",
                    "rating": 4.5
                },
                "driver": {
                    "id": 5,
                    "driver_id": "DRV-005",
                    "name": "John Banda",
                    "phone": "+265888123456",
                    "rating": 4.8
                },
                "pickup_location": {
                    "latitude": -13.9626,
                    "longitude": 33.7741,
                    "address": "Area 3, Lilongwe"
                },
                "destination": {
                    "latitude": -13.9833,
                    "longitude": 33.7833,
                    "address": "City Centre, Lilongwe"
                },
                "distance_km": 5.2,
                "duration_minutes": 15,
                "fare": 1725.0,
                "payment": {
                    "method": "tnm_mpamba",
                    "status": "completed",
                    "amount": 1725.0,
                    "platform_fee": 225.0,
                    "driver_earning": 1500.0,
                    "provider": "tnm_mpamba",
                    "transaction_id": "MPAMBA-2024-001234"
                },
                "requested_at": "2024-01-15T10:30:00Z",
                "completed_at": "2024-01-15T10:45:00Z",
                "rating": 5
            }
        }


class RideListResponse(BaseModel):
    """List of rides for history"""
    rides: List[RideResponse]
    total: int
    page: int
    per_page: int
    has_more: bool


# ============================================
# RIDE UPDATE SCHEMAS
# ============================================

class RideStatusUpdate(BaseModel):
    """Update ride status"""
    status: RideStatusEnum
    reason: Optional[str] = Field(None, description="Reason for cancellation (if applicable)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "cancelled_by_rider",
                "reason": "Driver taking too long"
            }
        }


class RideRatingRequest(BaseModel):
    """Rate a completed ride"""
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    comment: Optional[str] = Field(None, max_length=500, description="Optional feedback")
    tip_amount: Optional[float] = Field(None, ge=0, description="Optional tip for driver")
    
    @validator('tip_amount')
    def validate_tip(cls, v):
        if v and v > 50000:
            raise ValueError('Tip amount cannot exceed 50,000 MWK')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "rating": 5,
                "comment": "Great driver, very professional!",
                "tip_amount": 500.0
            }
        }


# ============================================
# PAYMENT SCHEMAS (Mobile Money)
# ============================================

class MobileMoneyPaymentRequest(BaseModel):
    """Request mobile money payment for a ride"""
    ride_id: str = Field(..., description="Ride ID to pay for")
    payment_method: PaymentMethodEnum = Field(..., description="tnm_mpamba or airtel_money")
    phone_number: str = Field(..., description="Mobile money phone number")
    
    @validator('payment_method')
    def validate_payment_method(cls, v):
        if v not in [PaymentMethodEnum.TNM_MPAMBA, PaymentMethodEnum.AIRTEL_MONEY]:
            raise ValueError('Payment method must be tnm_mpamba or airtel_money')
        return v
    
    @validator('phone_number')
    def format_phone(cls, v):
        """Format phone number to +265XXXXXXXXX"""
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if cleaned.startswith('0'):
            return '+265' + cleaned[1:]
        elif not cleaned.startswith('+'):
            return '+265' + cleaned
        return cleaned
    
    class Config:
        json_schema_extra = {
            "example": {
                "ride_id": "RIDE-2024-00100",
                "payment_method": "tnm_mpamba",
                "phone_number": "0888123456"
            }
        }


class MobileMoneyPaymentResponse(BaseModel):
    """Response after initiating mobile money payment"""
    success: bool
    message: str
    ride_id: str
    amount: float
    payment_method: str
    phone_number: str
    transaction_id: Optional[str] = None
    status: str = "pending"
    next_step: str = Field(..., description="Instructions for user (e.g., 'Check your phone for USSD prompt')")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Payment request sent successfully",
                "ride_id": "RIDE-2024-00100",
                "amount": 1725.0,
                "payment_method": "tnm_mpamba",
                "phone_number": "+265888123456",
                "transaction_id": "MPAMBA-2024-001234",
                "status": "pending",
                "next_step": "Please check your phone and enter your PIN to complete payment"
            }
        }


class PaymentStatusResponse(BaseModel):
    """Check payment status"""
    ride_id: str
    payment_status: PaymentStatusEnum
    transaction_id: Optional[str] = None
    amount: float
    completed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "ride_id": "RIDE-2024-00100",
                "payment_status": "completed",
                "transaction_id": "MPAMBA-2024-001234",
                "amount": 1725.0,
                "completed_at": "2024-01-15T10:31:00Z"
            }
        }


# ============================================
# DRIVER EARNING SCHEMAS
# ============================================

class DriverEarningResponse(BaseModel):
    """Driver earnings from a ride"""
    id: int
    ride_id: str
    ride_fare: float
    platform_fee: float
    driver_earning: float
    tip_amount: float
    status: str
    created_at: datetime
    cleared_at: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 50,
                "ride_id": "RIDE-2024-00100",
                "ride_fare": 1725.0,
                "platform_fee": 225.0,
                "driver_earning": 1500.0,
                "tip_amount": 100.0,
                "status": "cleared",
                "created_at": "2024-01-15T10:30:00Z",
                "cleared_at": "2024-01-16T00:00:00Z"
            }
        }


class DriverEarningsSummary(BaseModel):
    """Summary of driver earnings"""
    total_earnings: float
    available_balance: float
    pending_balance: float
    total_paid_out: float
    total_rides_completed: int
    this_week_earnings: float
    this_month_earnings: float
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_earnings": 150000.0,
                "available_balance": 25000.0,
                "pending_balance": 5000.0,
                "total_paid_out": 120000.0,
                "total_rides_completed": 85,
                "this_week_earnings": 15000.0,
                "this_month_earnings": 45000.0
            }
        }