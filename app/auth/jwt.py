"""
JWT Authentication Module for Kabaza Backend

This module handles:
- JWT token creation (access and refresh tokens)
- Token validation and decoding
- User authentication dependency injection
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================
# CONFIGURATION
# ============================================

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))  # 30 days

# Security scheme for OpenAPI docs
security = HTTPBearer(auto_error=False)


# ============================================
# TOKEN CREATION FUNCTIONS
# ============================================

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token for API authentication.
    
    Args:
        data: Dictionary containing user data (sub, phone, role, name, etc.)
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token string
        
    Example:
        token_data = {"sub": "123", "phone": "+265999888777", "role": "rider"}
        access_token = create_access_token(token_data)
    """
    to_encode = data.copy()
    
    # Set expiration time
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Add standard JWT claims
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    # Encode the JWT
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT refresh token for obtaining new access tokens.
    
    Refresh tokens have longer expiration and are used to get new access tokens
    without requiring the user to log in again.
    
    Args:
        data: Dictionary containing user data (sub, phone, role, etc.)
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT refresh token string
        
    Example:
        token_data = {"sub": "123", "phone": "+265999888777", "role": "rider"}
        refresh_token = create_refresh_token(token_data)
    """
    to_encode = data.copy()
    
    # Set expiration time (default: 30 days)
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Add standard JWT claims
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    # Encode the JWT
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def create_tokens_for_user(user_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Create both access and refresh tokens for a user.
    
    Args:
        user_data: Dictionary containing user information
        
    Returns:
        Dictionary with access_token and refresh_token
        
    Example:
        user = {"id": 1, "phone": "+265999888777", "role": "rider", "name": "John"}
        tokens = create_tokens_for_user(user)
        # Returns: {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}
    """
    token_data = {
        "sub": str(user_data.get("id")),
        "phone": user_data.get("phone"),
        "role": user_data.get("role", "rider"),
        "name": user_data.get("name", "")
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


# ============================================
# TOKEN DECODING AND VALIDATION
# ============================================

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload if valid, None if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
    except Exception:
        return None


def verify_token(token: str, token_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Verify a JWT token and optionally check its type.
    
    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")
        
    Returns:
        Token payload if valid, raises HTTPException if invalid
    """
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check token type if specified
    if token_type and payload.get("type") != token_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type. Expected {token_type} token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return payload


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verify an access token specifically.
    
    Args:
        token: Access token string
        
    Returns:
        Token payload if valid
    """
    return verify_token(token, token_type="access")


def verify_refresh_token(token: str) -> Dict[str, Any]:
    """
    Verify a refresh token specifically.
    
    Args:
        token: Refresh token string
        
    Returns:
        Token payload if valid
    """
    return verify_token(token, token_type="refresh")


# ============================================
# DEPENDENCY INJECTION FOR FASTAPI
# ============================================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    FastAPI dependency to get the current authenticated user.
    
    Use this in route handlers to require authentication:
        @router.get("/profile")
        async def get_profile(current_user: dict = Depends(get_current_user)):
            return {"user": current_user}
    
    Args:
        credentials: Bearer token credentials from request header
        
    Returns:
        Dictionary containing user information
        
    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Extract user information
        user_id = payload.get("sub")
        phone = payload.get("phone")
        role = payload.get("role")
        name = payload.get("name")
        token_type = payload.get("type")
        
        if user_id is None or phone is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Ensure it's an access token, not refresh token
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Access token required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return {
            "sub": user_id,
            "phone": phone,
            "role": role,
            "name": name or ""
        }
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency to get the current user (optional authentication).
    
    Use this when authentication is optional:
        @router.get("/public-profile")
        async def get_profile(current_user: Optional[dict] = Depends(get_current_user_optional)):
            if current_user:
                return {"message": f"Hello {current_user['name']}"}
            return {"message": "Hello Guest"}
    
    Args:
        credentials: Bearer token credentials from request header
        
    Returns:
        User dictionary if authenticated, None otherwise
    """
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        user_id = payload.get("sub")
        phone = payload.get("phone")
        
        if user_id is None or phone is None:
            return None
        
        return {
            "sub": user_id,
            "phone": phone,
            "role": payload.get("role"),
            "name": payload.get("name", "")
        }
        
    except (JWTError, Exception):
        return None


async def get_current_driver(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency to ensure the current user is a driver.
    
    Use this for driver-only endpoints:
        @router.post("/accept-ride")
        async def accept_ride(driver: dict = Depends(get_current_driver)):
            return {"message": f"Driver {driver['name']} accepting ride"}
    
    Args:
        current_user: User from get_current_user dependency
        
    Returns:
        User dictionary if they are a driver
        
    Raises:
        HTTPException: 403 if user is not a driver
    """
    if current_user.get("role") != "driver":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires driver privileges"
        )
    
    return current_user


async def get_current_rider(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency to ensure the current user is a rider.
    
    Use this for rider-only endpoints:
        @router.post("/request-ride")
        async def request_ride(rider: dict = Depends(get_current_rider)):
            return {"message": f"Rider {rider['name']} requesting ride"}
    
    Args:
        current_user: User from get_current_user dependency
        
    Returns:
        User dictionary if they are a rider
        
    Raises:
        HTTPException: 403 if user is not a rider
    """
    if current_user.get("role") != "rider":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires rider privileges"
        )
    
    return current_user


async def get_current_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency to ensure the current user is an admin.
    
    Use this for admin-only endpoints:
        @router.get("/admin/dashboard")
        async def admin_dashboard(admin: dict = Depends(get_current_admin)):
            return {"message": f"Welcome Admin {admin['name']}"}
    
    Args:
        current_user: User from get_current_user dependency
        
    Returns:
        User dictionary if they are an admin
        
    Raises:
        HTTPException: 403 if user is not an admin
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires admin privileges"
        )
    
    return current_user


# ============================================
# REFRESH TOKEN ENDPOINT HELPER
# ============================================

def refresh_access_token(refresh_token: str) -> Dict[str, str]:
    """
    Create a new access token from a valid refresh token.
    
    Args:
        refresh_token: Valid refresh token string
        
    Returns:
        Dictionary containing new access token
        
    Raises:
        HTTPException: If refresh token is invalid or expired
        
    Example:
        try:
            new_tokens = refresh_access_token(old_refresh_token)
            # Returns: {"access_token": "...", "token_type": "bearer"}
        except HTTPException:
            # Handle invalid refresh token
    """
    # Verify the refresh token
    payload = verify_refresh_token(refresh_token)
    
    # Extract user data (exclude JWT claims)
    token_data = {
        "sub": payload.get("sub"),
        "phone": payload.get("phone"),
        "role": payload.get("role"),
        "name": payload.get("name", "")
    }
    
    # Create new access token (refresh token remains valid until expiry)
    new_access_token = create_access_token(token_data)
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }


# ============================================
# UTILITY FUNCTIONS
# ============================================

def get_token_expiry(token: str) -> Optional[datetime]:
    """
    Get the expiration datetime of a token.
    
    Args:
        token: JWT token string
        
    Returns:
        Expiration datetime or None if token is invalid
    """
    payload = decode_token(token)
    if payload and "exp" in payload:
        return datetime.fromtimestamp(payload["exp"])
    return None


def is_token_expired(token: str) -> bool:
    """
    Check if a token is expired.
    
    Args:
        token: JWT token string
        
    Returns:
        True if expired, False if valid
    """
    expiry = get_token_expiry(token)
    if expiry:
        return datetime.utcnow() > expiry
    return True


def get_token_remaining_time(token: str) -> Optional[timedelta]:
    """
    Get the remaining time before token expires.
    
    Args:
        token: JWT token string
        
    Returns:
        Remaining timedelta or None if token is invalid/expired
    """
    expiry = get_token_expiry(token)
    if expiry:
        remaining = expiry - datetime.utcnow()
        if remaining.total_seconds() > 0:
            return remaining
    return None


# ============================================
# EXPORT LIST (for cleaner imports)
# ============================================

__all__ = [
    # Token creation
    "create_access_token",
    "create_refresh_token",
    "create_tokens_for_user",
    
    # Token verification
    "decode_token",
    "verify_token",
    "verify_access_token",
    "verify_refresh_token",
    
    # Dependencies
    "get_current_user",
    "get_current_user_optional",
    "get_current_driver",
    "get_current_rider",
    "get_current_admin",
    
    # Refresh functionality
    "refresh_access_token",
    
    # Utilities
    "get_token_expiry",
    "is_token_expired",
    "get_token_remaining_time",
    
    # Security scheme
    "security"
]