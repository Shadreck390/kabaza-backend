from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.db.database import get_db
from app.auth.jwt import get_current_user
from app.models.sql_models import Ride, Driver, RideStatus

router = APIRouter()


def _resolve_driver_by_identifier(db: Session, driver_identifier: str) -> Optional[Driver]:
    """Match Driver row by user id, driver pk, phone, or legacy driver_id string."""
    driver = None
    if driver_identifier.isdigit():
        n = int(driver_identifier)
        driver = db.query(Driver).filter(Driver.user_id == n).first()
        if not driver:
            driver = db.query(Driver).filter(Driver.id == n).first()
    if not driver:
        driver = db.query(Driver).filter(Driver.phone == driver_identifier).first()
    if not driver:
        driver = db.query(Driver).filter(Driver.driver_id == driver_identifier).first()
    return driver


def _driver_matches_current_user(current_user: dict, driver: Driver) -> bool:
    if current_user.get("role") == "admin":
        return True
    sub = current_user.get("sub")
    if driver.user_id is not None:
        return str(sub) == str(driver.user_id)
    token_phone = current_user.get("phone")
    return (
        token_phone is not None
        and driver.phone is not None
        and str(token_phone) == str(driver.phone)
    )


# ============================================================================
# DRIVER ACTIVE RIDE ENDPOINT (Fixes the 404 error)
# ============================================================================

@router.get("/{driver_identifier}/active-ride")
async def get_driver_active_ride(
    driver_identifier: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get active ride for a driver.
    Accepts user id (numeric), driver table id, phone, or legacy driver_id string.
    """
    driver = _resolve_driver_by_identifier(db, driver_identifier)
    if not driver:
        return {
            "activeRide": None,
            "hasActiveRide": False,
            "message": "Driver not found",
        }

    if not _driver_matches_current_user(current_user, driver):
        raise HTTPException(status_code=403, detail="Access denied")

    active_ride = db.query(Ride).filter(
        and_(
            Ride.driver_id == driver.id,
            Ride.status.in_(
                [RideStatus.ACCEPTED, RideStatus.DRIVER_ARRIVED, RideStatus.ONGOING]
            ),
        )
    ).first()

    if not active_ride:
        return {
            "activeRide": None,
            "hasActiveRide": False,
        }

    return {
        "activeRide": {
            "id": active_ride.ride_id,
            "rideId": active_ride.ride_id,
            "status": active_ride.status.value,
            "pickup": active_ride.pickup_location,
            "destination": active_ride.destination,
            "fare": active_ride.fare,
            "riderName": active_ride.rider_name or "Customer",
            "distance": active_ride.distance_km,
            "duration": active_ride.duration_minutes,
        },
        "hasActiveRide": True,
    }

# ============================================================================
# DRIVER STATUS ENDPOINTS
# ============================================================================

@router.post("/{driver_id}/status")
async def update_driver_status(
    driver_id: str,
    status_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update driver's online/offline status"""
    if current_user.get("id") != driver_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    status = status_data.get("status", "offline")
    location = status_data.get("location")
    
    # Find or create driver record
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    if not driver:
        driver = Driver(driver_id=driver_id)
        db.add(driver)
    
    driver.driver_status = status
    driver.last_status_update = datetime.utcnow()
    
    if location:
        driver.last_location = location
    
    db.commit()
    
    return {
        "success": True,
        "driverId": driver_id,
        "status": status,
        "message": f"Driver status updated to {status}"
    }

@router.get("/{driver_id}/status")
async def get_driver_status(
    driver_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current driver status"""
    if current_user.get("id") != driver_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    
    if not driver:
        return {
            "driverId": driver_id,
            "status": "offline",
            "isOnline": False
        }
    
    return {
        "driverId": driver_id,
        "status": driver.driver_status,
        "isOnline": driver.driver_status == "available",
        "lastLocation": driver.last_location,
        "lastUpdate": driver.last_status_update
    }

# ============================================================================
# EARNINGS ENDPOINTS
# ============================================================================

@router.get("/{driver_id}/earnings/today")
async def get_driver_earnings_today(
    driver_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get driver's earnings for today"""
    if current_user.get("id") != driver_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    total = db.query(Ride).filter(
        and_(
            Ride.driver_id == driver_id,
            Ride.status == RideStatus.COMPLETED,
            Ride.completed_at >= today_start
        )
    ).with_entities(db.func.sum(Ride.fare)).scalar() or 0.0
    
    return {
        "total": total,
        "currency": "MK",
        "driverId": driver_id,
        "date": datetime.utcnow().date().isoformat()
    }

@router.get("/{driver_id}/rides/completed/today")
async def get_driver_rides_completed_today(
    driver_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get count of rides completed today"""
    if current_user.get("id") != driver_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    count = db.query(Ride).filter(
        and_(
            Ride.driver_id == driver_id,
            Ride.status == RideStatus.COMPLETED,
            Ride.completed_at >= today_start
        )
    ).count()
    
    return {
        "count": count,
        "driverId": driver_id,
        "date": datetime.utcnow().date().isoformat()
    }