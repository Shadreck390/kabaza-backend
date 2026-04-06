from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True)
    phone = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, default="rider")
    is_verified = Column(Boolean, default=False)
    profile_image = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())