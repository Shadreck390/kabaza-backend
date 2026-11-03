from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.auth.jwt import get_current_user
from app.models.user import User
from app.models.sql_models import Ride

router = APIRouter()

# ============================================================================
# DRIVER STATUS
# ============================================================================

@router.post("/status")
async def update_driver_status(
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    """Update driver's online/offline status."""
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can update status")

    new_status = body.get("status", "offline")
    if new_status not in ["available", "offline", "on_trip"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    # For now, just return success (we'll add a driver_status column later)
    return {"success": True, "status": new_status}


# ============================================================================
# DRIVER ACTIVE RIDE
# ============================================================================

@router.get("/active-ride")
async def get_driver_active_ride(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the driver's current active ride (if any)."""
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers have active rides")

    driver_id = current_user.get("id")

    active_ride = (
        db.query(Ride)
        .filter(
            Ride.driver_id == driver_id,
            Ride.status.in_(["accepted", "in_progress"]),
        )
        .first()
    )

    if not active_ride:
        return {"activeRide": None, "hasActiveRide": False}

    return {
        "activeRide": {
            "id": active_ride.ride_id,
            "rideId": active_ride.ride_id,
            "status": active_ride.status,
            "pickup": active_ride.pickup_location,
            "destination": active_ride.destination,
            "fare": float(active_ride.fare) if active_ride.fare else 0,
            "riderName": active_ride.rider_name or "Customer",
            "distance": float(active_ride.distance_km) if active_ride.distance_km else 0,
        },
        "hasActiveRide": True,
    }


# ============================================================================
# DRIVER EARNINGS (Today)
# ============================================================================

@router.get("/earnings/today")
async def get_driver_earnings_today(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get driver's earnings for today."""
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers have earnings")

    driver_id = current_user.get("id")
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    total = (
        db.query(Ride)
        .filter(
            Ride.driver_id == driver_id,
            Ride.status == "completed",
            Ride.requested_at >= today_start,
        )
        .with_entities(db.func.sum(Ride.fare))
        .scalar()
        or 0.0
    )

    return {
        "total": float(total),
        "currency": "MK",
        "date": today_start.date().isoformat(),
    }


# ============================================================================
# DRIVER RIDES COMPLETED TODAY
# ============================================================================

@router.get("/rides/completed/today")
async def get_driver_rides_completed_today(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get count of rides completed today."""
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers have rides")

    driver_id = current_user.get("id")
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    count = (
        db.query(Ride)
        .filter(
            Ride.driver_id == driver_id,
            Ride.status == "completed",
            Ride.requested_at >= today_start,
        )
        .count()
    )

    return {"count": count, "date": today_start.date().isoformat()}