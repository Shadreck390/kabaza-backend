from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import Optional
from app.db.database import get_db
from app.models.user import User
from app.auth.jwt import create_access_token, verify_token
import random
from datetime import datetime, timedelta
from app.models.otp import OTP  # You need to create this model first

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Request/Response Models
class UserRegister(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    password: str
    role: str = "rider"

class UserLogin(BaseModel):
    phone: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int

class UserResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str]
    role: str
    is_verified: bool

# ========== EXISTING ENDPOINTS (KEEP THESE) ==========
@router.post("/register", response_model=TokenResponse)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.phone == user_data.phone).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    hashed_password = pwd_context.hash(user_data.password)
    
    new_user = User(
        name=user_data.name,
        phone=user_data.phone,
        email=user_data.email,
        password=hashed_password,
        role=user_data.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    token = create_access_token({"sub": str(new_user.id), "role": new_user.role})
    
    return {"access_token": token, "token_type": "bearer", "user_id": new_user.id}

@router.post("/login", response_model=TokenResponse)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == user_data.phone).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not pwd_context.verify(user_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": str(user.id), "role": user.role})
    
    return {"access_token": token, "token_type": "bearer", "user_id": user.id}

@router.get("/me", response_model=UserResponse)
def get_me(user_data: dict = Depends(verify_token), db: Session = Depends(get_db)):
    user_id = int(user_data.get("sub"))
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# ========== NEW OTP ENDPOINTS (ADD THESE) ==========
@router.post("/send-otp")
def send_otp(phone_data: dict, db: Session = Depends(get_db)):
    """Send OTP to phone number"""
    phone = phone_data.get("phone")
    
    # Generate 6-digit OTP
    otp_code = str(random.randint(100000, 999999))
    
    # Delete old OTPs
    db.query(OTP).filter(OTP.phone == phone).delete()
    
    # Create new OTP
    new_otp = OTP(
        phone=phone,
        code=otp_code,
        expires_at=datetime.utcnow() + timedelta(minutes=5)
    )
    db.add(new_otp)
    db.commit()
    
    # In production, send SMS here
    print(f"📱 OTP for {phone}: {otp_code}")
    
    return {"message": "OTP sent successfully", "otp": otp_code}  # Remove otp in production

@router.post("/verify-otp")
def verify_otp(verify_data: dict, db: Session = Depends(get_db)):
    """Verify OTP"""
    phone = verify_data.get("phone")
    code = verify_data.get("code")
    
    otp_record = db.query(OTP).filter(
        OTP.phone == phone,
        OTP.code == code,
        OTP.is_used == 0,
        OTP.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    # Mark as used
    otp_record.is_used = 1
    db.commit()
    
    return {"message": "OTP verified successfully"}