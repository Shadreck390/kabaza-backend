from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kabaza.db")

# SQLite specific - connect_args needed
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}  # Only needed for SQLite
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Import all models to create tables
# ✅ FIXED: Import all models, not just Ride and Driver
from app.models.sql_models import (
    Ride, Driver, User, Rider, Vehicle, 
    DriverEarning, Payout, RiderPaymentMethod,
    FavoriteLocation, WalletTransaction, OTP
)