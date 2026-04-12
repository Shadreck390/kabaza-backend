from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import random
import redis
import os
import hashlib
import logging
import secrets
from pydantic import BaseModel, validator

from app.db.database import get_db
from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    create_tokens_for_user,
    get_current_user
)

from app.models.user import User
from app.models.otp import OTP as OTPModel  

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================
# REDIS CONFIGURATION (Production)
# ============================================
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("✅ Redis connected successfully")
except Exception as e:
    logger.warning(f"⚠️ Redis connection failed: {e}. Using in-memory fallback.")
    redis_client = None

# Fallback to in-memory if Redis is down
in_memory_fallback = {}

# ============================================
# SECURITY UTILITIES (MOVED TO TOP)
# ============================================
def constant_time_compare(val1: str, val2: str) -> bool:
    """
    Constant-time string comparison to prevent timing attacks
    """
    if len(val1) != len(val2):
        return False
    
    result = 0
    for x, y in zip(val1, val2):
        result |= ord(x) ^ ord(y)
    return result == 0

# ============================================
# PYDANTIC MODELS (Request/Response Validation)
# ============================================
class SendOTPRequest(BaseModel):
    phone: str
    
    @validator('phone')
    def validate_phone(cls, v):
        # Remove any non-digit characters except +
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        if len(cleaned.replace('+', '')) < 8:
            raise ValueError('Phone number must have at least 8 digits')
        return cleaned

class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str
    role: Optional[str] = "rider"
    name: Optional[str] = ""
    
    @validator('phone')
    def validate_phone(cls, v):
        cleaned = ''.join(c for c in v if c.isdigit() or c == '+')
        return cleaned
    
    @validator('otp')
    def validate_otp(cls, v):
        if len(v) != 6 or not v.isdigit():
            raise ValueError('OTP must be 6 digits')
        return v

class ResendOTPRequest(BaseModel):
    phone: str

# ============================================
# HELPER FUNCTIONS
# ============================================
def generate_otp() -> str:
    """Generate cryptographically secure 6-digit OTP"""
    return str(random.SystemRandom().randint(100000, 999999))

def get_otp_key(phone: str) -> str:
    """Generate consistent Redis key for OTP"""
    return f"otp:{phone}"

def get_rate_limit_key(phone: str) -> str:
    """Generate Redis key for rate limiting"""
    return f"otp_rate:{phone}"

def get_attempts_key(phone: str) -> str:
    """Generate Redis key for verification attempts"""
    return f"otp_attempts:{phone}"

def store_otp(phone: str, otp: str, ttl_minutes: int = 5) -> bool:
    """Store OTP in Redis with TTL"""
    try:
        if redis_client:
            key = get_otp_key(phone)
            redis_client.setex(key, timedelta(minutes=ttl_minutes), otp)
            logger.info(f"OTP stored in Redis for {phone}")
        else:
            in_memory_fallback[phone] = {
                "otp": otp,
                "expires_at": datetime.utcnow() + timedelta(minutes=ttl_minutes)
            }
            logger.info(f"OTP stored in memory for {phone}")
        return True
    except Exception as e:
        logger.error(f"Storage error, using fallback: {e}")
        in_memory_fallback[phone] = {
            "otp": otp,
            "expires_at": datetime.utcnow() + timedelta(minutes=ttl_minutes)
        }
        return True

def get_stored_otp(phone: str) -> Optional[str]:
    """Retrieve OTP from Redis or fallback"""
    # Try Redis first
    if redis_client:
        try:
            key = get_otp_key(phone)
            otp = redis_client.get(key)
            if otp:
                return otp
        except Exception as e:
            logger.error(f"Redis get error: {e}")
    
    # Fallback to in-memory
    stored = in_memory_fallback.get(phone)
    if stored and datetime.utcnow() <= stored["expires_at"]:
        return stored["otp"]
    elif phone in in_memory_fallback:
        del in_memory_fallback[phone]
    
    return None

def delete_otp(phone: str) -> None:
    """Delete OTP after successful verification"""
    if redis_client:
        try:
            redis_client.delete(get_otp_key(phone))
            redis_client.delete(get_attempts_key(phone))
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
    
    if phone in in_memory_fallback:
        del in_memory_fallback[phone]

def check_rate_limit(phone: str) -> tuple:
    """
    Check if phone is rate limited
    Returns: (is_allowed, seconds_until_retry)
    """
    if not redis_client:
        return True, 0  # No rate limiting without Redis
    
    try:
        key = get_rate_limit_key(phone)
        count = redis_client.get(key)
        
        if count and int(count) >= 3:
            ttl = redis_client.ttl(key)
            return False, ttl if ttl > 0 else 60
        
        # Increment counter with 15 minute window
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 900)  # 15 minutes
        pipe.execute()
        
        return True, 0
    except Exception as e:
        logger.error(f"Rate limit check error: {e}")
        return True, 0  # Fail open if Redis is down

def increment_attempts(phone: str) -> int:
    """Increment failed verification attempts"""
    if not redis_client:
        # Simple in-memory attempt tracking
        key = f"attempts_{phone}"
        current = in_memory_fallback.get(key, 0) + 1
        in_memory_fallback[key] = current
        return current
    
    try:
        key = get_attempts_key(phone)
        count = redis_client.incr(key)
        redis_client.expire(key, 300)  # 5 minute window
        return count
    except Exception as e:
        logger.error(f"Attempt increment error: {e}")
        return 0

def reset_attempts(phone: str) -> None:
    """Reset failed attempts after successful verification"""
    if redis_client:
        try:
            redis_client.delete(get_attempts_key(phone))
        except Exception as e:
            logger.error(f"Reset attempts error: {e}")
    
    # Clear in-memory attempts
    key = f"attempts_{phone}"
    if key in in_memory_fallback:
        del in_memory_fallback[key]

def get_failed_attempts(phone: str) -> int:
    """Get number of failed verification attempts"""
    if not redis_client:
        return in_memory_fallback.get(f"attempts_{phone}", 0)
    
    try:
        count = redis_client.get(get_attempts_key(phone))
        return int(count) if count else 0
    except Exception:
        return 0

# ============================================
# ENDPOINTS
# ============================================

@router.post("/send-otp")
async def send_otp(request: SendOTPRequest):
    """
    Send OTP to user's phone number
    
    Rate Limits:
    - 3 requests per 15 minutes
    - OTP valid for 5 minutes
    """
    phone = request.phone
    
    # Rate limit check
    is_allowed, retry_after = check_rate_limit(phone)
    if not is_allowed:
        logger.warning(f"Rate limit exceeded for {phone}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many OTP requests. Please try again in {retry_after} seconds."
        )
    
    # Generate and store OTP
    otp = generate_otp()
    store_otp(phone, otp, ttl_minutes=5)
    
    # In production, integrate with SMS provider here
    # sms_provider.send(phone, f"Your Kabaza verification code is: {otp}")
    
    logger.info(f"📱 OTP sent to {phone}: {otp}")
    
    return {
        "success": True,
        "message": "OTP sent successfully",
        "expires_in": 300,  # 5 minutes in seconds
        # DEBUG ONLY - Remove in production
        "debug_otp": otp if os.getenv("ENVIRONMENT") == "development" else None
    }


@router.post("/verify-otp")
async def verify_otp(
    request: VerifyOTPRequest,
    db: Session = Depends(get_db)
):
    """
    Verify OTP and authenticate user
    
    Returns:
    - access_token: JWT token for API authentication
    - refresh_token: Token for refreshing access token
    - user: User information
    - requires_profile_completion: Boolean indicating if profile needs completion
    """
    phone = request.phone
    otp = request.otp
    role = request.role
    name = request.name
    
    logger.info(f"🔐 Verifying OTP for {phone}")
    
    # Check failed attempts
    failed_attempts = get_failed_attempts(phone)
    if failed_attempts >= 5:
        logger.warning(f"Too many failed attempts for {phone}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please request a new OTP after 5 minutes."
        )
    
    # Retrieve stored OTP
    stored_otp = get_stored_otp(phone)
    
    if not stored_otp:
        logger.warning(f"No OTP found or OTP expired for {phone}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not requested. Please request a new OTP."
        )
    
    # Compare OTPs (constant-time comparison to prevent timing attacks)
    if not constant_time_compare(stored_otp, otp):
        attempts = increment_attempts(phone)
        remaining = 5 - attempts
        logger.warning(f"Invalid OTP for {phone}. Attempt {attempts}/5")
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP. {remaining} attempts remaining."
        )
    
    # OTP is valid - clean up
    delete_otp(phone)
    reset_attempts(phone)
    
    logger.info(f"✅ OTP verified successfully for {phone}")
    
    # Find or create user
    user = db.query(User).filter(User.phone == phone).first()
    is_new_user = False
    
    if not user:
        logger.info(f"Creating new user for {phone}")
        is_new_user = True
        
        # Handle password for new users (required field in model)
        # Generate a random secure password since they're using OTP auth
        import secrets
        random_password = secrets.token_urlsafe(16)
        
        user = User(
            phone=phone,
            name=name or f"User_{phone[-4:]}",  # Default name if not provided
            email=None,  # Can be updated later
            password=random_password,  # Required field - will hash automatically if model has setter
            role=role,
            is_verified=True,
            created_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        logger.info(f"Existing user found: {user.id}")
        # Update role if changed
        if user.role != role:
            user.role = role
            db.commit()
            db.refresh(user)
    
    # Check if profile needs completion
    requires_profile_completion = (
        is_new_user or 
        not user.name or 
        user.name.startswith("User_") or
        not user.email
    )
    
    # Create tokens using the convenience function
    tokens = create_tokens_for_user({
        "id": user.id,
        "phone": user.phone,
        "role": user.role,
        "name": user.name or ""
    })
    
    # Prepare user response
    user_response = {
        "id": user.id,
        "phone": user.phone,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_verified": user.is_verified,
        "profile_image": getattr(user, 'profile_image', None),  # Safe access
        "created_at": user.created_at.isoformat() if user.created_at else None
    }
    
    logger.info(f"🎉 User authenticated successfully: {user.id}")
    
    return {
        "success": True,
        "message": "OTP verified successfully",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": tokens["token_type"],
        "user": user_response,
        "requires_profile_completion": requires_profile_completion,
        "is_new_user": is_new_user
    }


@router.post("/resend-otp")
async def resend_otp(request: ResendOTPRequest):
    """
    Resend OTP to phone number
    
    This endpoint:
    - Invalidates any existing OTP
    - Respects the same rate limits as /send-otp
    """
    phone = request.phone
    
    # Rate limit check (same as send-otp)
    is_allowed, retry_after = check_rate_limit(phone)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many OTP requests. Please try again in {retry_after} seconds."
        )
    
    # Delete any existing OTP
    delete_otp(phone)
    
    # Generate and store new OTP
    otp = generate_otp()
    store_otp(phone, otp, ttl_minutes=5)
    
    logger.info(f"🔄 OTP resent to {phone}: {otp}")
    
    return {
        "success": True,
        "message": "OTP resent successfully",
        "expires_in": 300,
        "debug_otp": otp if os.getenv("ENVIRONMENT") == "development" else None
    }


@router.post("/refresh")
async def refresh_access_token_endpoint(refresh_data: dict):
    """
    Get new access token using refresh token
    """
    from app.auth.jwt import refresh_access_token
    
    refresh_token = refresh_data.get("refresh_token")
    
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required"
        )
    
    try:
        new_tokens = refresh_access_token(refresh_token)
        return {
            "success": True,
            **new_tokens
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Refresh token error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """
    Logout user
    
    Note: JWT tokens are stateless. This endpoint exists for:
    - Logging purposes
    - Future blacklist implementation
    """
    logger.info(f"👋 User logged out: {current_user.get('sub')}")
    
    # Future: Add token to blacklist in Redis
    
    return {
        "success": True,
        "message": "Logged out successfully"
    }


@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user information"""
    return {
        "success": True,
        "user": current_user
    }


@router.post("/register")
async def register_user(
    registration_data: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Complete user profile registration after OTP verification

    Expected payload:
    {
        "name": "Full Name",
        "email": "user@example.com",
        "profile_image": "optional_url",
        "date_of_birth": "YYYY-MM-DD",
        "gender": "M/F/Other"
    }

    Note: date_of_birth and gender are accepted for clients; the User model
    currently persists name, email, profile_image, and verification status.
    """
    try:
        user_id = int(current_user.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    new_email = registration_data.get("email")
    if new_email and new_email != user.email:
        taken = (
            db.query(User)
            .filter(User.email == new_email, User.id != user_id)
            .first()
        )
        if taken:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already registered to another account",
            )

    if registration_data.get("name") is not None:
        user.name = registration_data.get("name") or user.name
    if new_email is not None:
        user.email = new_email
    user.is_verified = True

    if registration_data.get("profile_image"):
        user.profile_image = registration_data.get("profile_image")

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not update profile (e.g. email already in use)",
        )

    logger.info(f"User profile updated: {user.id}")

    return {
        "success": True,
        "message": "Profile updated successfully",
        "user": {
            "id": user.id,
            "phone": user.phone,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_verified": user.is_verified,
            "profile_image": user.profile_image,
        },
    }


# ============================================
# HEALTH CHECK ENDPOINT
# ============================================
@router.get("/health")
async def auth_health():
    """Check auth service health"""
    redis_status = "healthy"
    
    if redis_client:
        try:
            redis_client.ping()
        except Exception:
            redis_status = "degraded"
    else:
        redis_status = "fallback_mode"
    
    return {
        "service": "auth",
        "status": "healthy",
        "redis": redis_status,
        "timestamp": datetime.utcnow().isoformat()
    }