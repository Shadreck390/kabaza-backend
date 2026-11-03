from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
import uuid
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.auth.jwt import get_current_user
from app.models.sql_models import Ride

router = APIRouter()

def generate_ride_id():
    """Generate a unique ride ID"""
    return f"RD{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"

@router.post("/book")
async def book_ride(
    ride_request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new ride request - matches your PostgreSQL table"""
    rider_id = current_user.get("id")
    if not rider_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    ride_id = generate_ride_id()
    driver_id = ride_request.get("driver_id")
    scheduled_for_str = ride_request.get("scheduled_for")
    is_scheduled = ride_request.get("is_scheduled", False)
    scheduled_for = None

    if scheduled_for_str is not None:
        if not isinstance(scheduled_for_str, str):
            raise HTTPException(status_code=422, detail="Invalid scheduled_for datetime")
        try:
            scheduled_for = datetime.fromisoformat(scheduled_for_str.replace("Z", "+00:00"))
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid scheduled_for datetime") from error

    if is_scheduled and not scheduled_for:
        raise HTTPException(status_code=422, detail="scheduled_for is required for scheduled rides")

    new_ride = Ride(
        ride_id=ride_id,
        rider_id=rider_id,
        rider_name=current_user.get("full_name") or current_user.get("name", "Customer"),
        driver_id=driver_id,
        pickup_location=ride_request.get("pickup_location", {}),
        destination=ride_request.get("destination", {}),
        payment_method=ride_request.get("payment_method", "cash"),
        status="scheduled" if is_scheduled else "requested",
        fare=ride_request.get("fare", 0),
        distance_km=ride_request.get("distance_km", 0),
        duration_minutes=ride_request.get("duration_minutes", 0),
        requested_at=datetime.utcnow(),
        scheduled_for=scheduled_for,
        is_scheduled=is_scheduled,
    )

    try:
        db.add(new_ride)
        db.commit()
        db.refresh(new_ride)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save ride: {str(e)}")

    return {
        "success": True,
        "rideId": ride_id,
        "message": "Ride booked successfully",
    }

@router.get("/available")
async def get_available_rides(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Driver endpoint: Get all pending ride requests"""
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can view available rides")

    pending_rides = db.query(Ride).filter(Ride.status == "requested").all()

    rides_list = []
    for ride in pending_rides:
        rides_list.append({
            "id": ride.id,
            "ride_id": ride.ride_id,
            "pickup_location": ride.pickup_location,
            "destination": ride.destination,
            "fare": float(ride.fare) if ride.fare else 0,
            "distance_km": float(ride.distance_km) if ride.distance_km else 0,
            "rider_name": ride.rider_name,
            "requested_at": ride.requested_at.isoformat() if ride.requested_at else None,
        })

    return {
        "rides": rides_list,
        "count": len(rides_list),
    }

@router.get("/history")
async def get_ride_history(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the logged-in rider's past rides"""
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Fetch all rides for this rider, newest first
    rides = (
        db.query(Ride)
        .filter(Ride.rider_id == user_id)
        .order_by(Ride.requested_at.desc())
        .all()
    )

    history = []
    for ride in rides:
        # Calculate duration in minutes
        duration_min = ride.duration_minutes or 0

        history.append({
            "id": ride.ride_id,               # String ID (RD2026...)
            "numericId": ride.id,             # Integer ID (for ratings)
            "status": ride.status,
            "pickup": ride.pickup_location.get("address", "Unknown"),
            "destination": ride.destination.get("address", "Unknown"),
            "fare": float(ride.fare) if ride.fare else 0,
            "distance_km": float(ride.distance_km) if ride.distance_km else 0,
            "duration_min": duration_min,
            "driver_name": ride.driver_name or "Driver Assigned",
            "payment_method": ride.payment_method,
            "created_at": ride.requested_at.isoformat() if ride.requested_at else None,
        })

    return {"rides": history, "count": len(history)}

@router.get("/earnings")
async def get_driver_earnings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get driver earnings: today, this week, this month, all-time"""
    driver_id = current_user.get("id")
    if not driver_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers have earnings")

    from sqlalchemy import func
    from datetime import timedelta

    now = datetime.utcnow()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = start_of_today - timedelta(days=now.weekday())
    start_of_month = start_of_today.replace(day=1)

    def stats_for_period(since):
        query = db.query(
            func.count(Ride.id).label("rides"),
            func.coalesce(func.sum(Ride.fare), 0).label("amount"),
        ).filter(
            Ride.driver_id == driver_id,
            Ride.status == "completed",
            Ride.requested_at >= since,
        )
        result = query.first()
        return {
            "rides": result.rides or 0,
            "amount": float(result.amount or 0),
            "hours": 0,
        }

    total_query = db.query(
        func.count(Ride.id).label("rides"),
        func.coalesce(func.sum(Ride.fare), 0).label("amount"),
    ).filter(
        Ride.driver_id == driver_id,
        Ride.status == "completed",
    )
    total_result = total_query.first()

    recent = (
        db.query(Ride)
        .filter(Ride.driver_id == driver_id, Ride.status == "completed")
        .order_by(Ride.requested_at.desc())
        .limit(5)
        .all()
    )

    recent_list = [
        {
            "id": ride.id,
            "type": "ride",
            "amount": float(ride.fare) if ride.fare else 0,
            "time": ride.requested_at.strftime("%I:%M %p") if ride.requested_at else "",
            "passengerName": ride.rider_name or "Passenger",
            "status": "completed",
        }
        for ride in recent
    ]

    return {
        "today": stats_for_period(start_of_today),
        "week": stats_for_period(start_of_week),
        "month": stats_for_period(start_of_month),
        "total": {
            "rides": total_result.rides or 0,
            "amount": float(total_result.amount or 0),
            "hours": 0,
        },
        "recent_earnings": recent_list,
    }

@router.get("/driver/history")
async def get_driver_trip_history(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the driver's completed trips"""
    driver_id = current_user.get("id") or current_user.get("sub")
    if not driver_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        driver_id = int(driver_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Not authenticated")

    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers have trip history")

    trips = (
        db.query(Ride)
        .filter(Ride.driver_id == driver_id, Ride.status == "completed")
        .order_by(Ride.requested_at.desc())
        .all()
    )

    result = []
    for ride in trips:
        result.append({
            "id": ride.ride_id,
            "numericId": ride.id,
            "date": ride.requested_at.strftime("%Y-%m-%dT%H:%M:%S") if ride.requested_at else None,
            "passenger_name": ride.rider_name or "Passenger",
            "pickup": ride.pickup_location.get("address", "Unknown") if ride.pickup_location else "",
            "destination": ride.destination.get("address", "Unknown") if ride.destination else "",
            "fare": float(ride.fare) if ride.fare else 0,
            "distance_km": float(ride.distance_km) if ride.distance_km else 0,
            "duration_minutes": ride.duration_minutes or 0,
            "payment_method": ride.payment_method or "cash",
            "status": ride.status,
        })

    return {"trips": result, "count": len(result)}

@router.get("/{ride_id}")
async def get_ride_details(
    ride_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get ride status (used by frontend polling)"""
    ride = db.query(Ride).filter(Ride.ride_id == ride_id).first()

    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")

    user_id = current_user.get("id")
    if ride.rider_id != user_id and ride.driver_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": ride.id,
        "ride_id": ride.ride_id,
        "status": ride.status,
        "pickup_location": ride.pickup_location,
        "destination": ride.destination,
        "fare": float(ride.fare) if ride.fare else 0,
        "rider_name": ride.rider_name,
        "driver_name": ride.driver_name,
        "driver_id": ride.driver_id,
    }

@router.post("/{ride_id}/accept")
async def accept_ride(
    ride_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Driver accepts a ride request"""
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can accept rides")

    ride = db.query(Ride).filter(Ride.ride_id == ride_id).first()

    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")

    if ride.status != "requested":
        raise HTTPException(status_code=400, detail="Ride is no longer available")

    ride.driver_id = current_user.get("id")
    ride.driver_name = current_user.get("name")
    ride.status = "accepted"
    ride.accepted_at = datetime.utcnow()

    db.commit()

    return {"success": True, "message": "Ride accepted successfully"}

@router.put("/{ride_id}/status")
async def update_ride_status(
    ride_id: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update ride status (driver marks as in progress or completed)"""
    ride = db.query(Ride).filter(Ride.ride_id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")

    if ride.driver_id != current_user.get("id"):
        raise HTTPException(
            status_code=403,
            detail="Only the assigned driver can update this ride",
        )

    new_status = body.get("status")
    if new_status not in ["accepted", "in_progress", "completed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    ride.status = new_status
    if new_status == "completed" and body.get("final_fare") is not None:
        ride.fare = body["final_fare"]

    db.commit()
    db.refresh(ride)

    return {"success": True, "status": ride.status, "message": "Status updated"}

@router.put("/{ride_id}/cancel")
async def cancel_ride(
    ride_id: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a ride"""
    ride = db.query(Ride).filter(Ride.ride_id == ride_id).first()

    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")

    user_id = current_user.get("id")
    user_role = current_user.get("role")

    if ride.rider_id == user_id:
        ride.status = "cancelled_by_rider"
    elif ride.driver_id == user_id:
        ride.status = "cancelled_by_driver"
    else:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this ride")

    ride.cancelled_at = datetime.utcnow()
    ride.cancellation_reason = reason

    db.commit()

    return {"success": True, "message": "Ride cancelled successfully"}