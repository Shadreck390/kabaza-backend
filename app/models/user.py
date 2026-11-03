from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date
from app.db.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=True)
    role = Column(String, default="rider")
    password = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    profile_image = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)