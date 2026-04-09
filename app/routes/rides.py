from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.db.database import get_db
from app.auth.jwt import get_current_user
from app.models.sql_models import Ride, RideStatus

router = APIRouter()

def generate_ride_id():
    """Generate a unique ride ID"""
    return f"RD{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"

@router.get("/nearby")
async def get_nearby_rides(
    lat: float,
    lng: float,
    radius_km: float = 5,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get nearby ride requests for driver"""
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can access this endpoint")
    
    pending_rides = db.query(Ride).filter(
        Ride.status == RideStatus.REQUESTED
    ).limit(20).all()
    
    rides_list = []
    for ride in pending_rides:
        rides_list.append({
            "id": ride.id,
            "ride_id": ride.ride_id,
            "pickup_location": ride.pickup_location,
            "destination": ride.destination,
            "fare": ride.fare,
            "distance_km": ride.distance_km,
            "rider_name": ride.rider_name,
        })
    
    return {
        "rides": rides_list,
        "count": len(rides_list)
    }

@router.get("/{ride_id}")
async def get_ride_details(
    ride_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific ride"""
    ride = db.query(Ride).filter(Ride.ride_id == ride_id).first()
    
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    if ride.rider_id != user_id and ride.driver_id != user_id and user_role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "id": ride.id,
        "ride_id": ride.ride_id,
        "status": ride.status.value,
        "pickup_location": ride.pickup_location,
        "destination": ride.destination,
        "fare": ride.fare,
        "rider_name": ride.rider_name,
        "driver_name": ride.driver_name,
    }

@router.post("/book")
async def book_ride(
    ride_request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new ride request"""
    ride_id = generate_ride_id()
    
    new_ride = Ride(
        ride_id=ride_id,
        rider_id=current_user.get("id"),
        rider_name=current_user.get("name", "Customer"),
        pickup_location=ride_request.get("pickup_location", {}),
        destination=ride_request.get("destination", {}),
        waypoints=ride_request.get("waypoints", []),
        payment_method=ride_request.get("payment_method", "cash"),
        status=RideStatus.REQUESTED,
        fare=ride_request.get("fare", 0),
        distance_km=ride_request.get("distance_km", 0),
        duration_minutes=ride_request.get("duration_minutes", 0),
        requested_at=datetime.utcnow(),
        is_scheduled=ride_request.get("is_scheduled", False),
        scheduled_for=ride_request.get("scheduled_for"),
    )
    
    db.add(new_ride)
    db.commit()
    db.refresh(new_ride)
    
    return {
        "success": True,
        "rideId": ride_id,
        "message": "Ride booked successfully"
    }

@router.post("/{ride_id}/accept")
async def accept_ride(
    ride_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Driver accepts a ride request"""
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can accept rides")
    
    ride = db.query(Ride).filter(Ride.ride_id == ride_id).first()
    
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    if ride.status != RideStatus.REQUESTED:
        raise HTTPException(status_code=400, detail="Ride is no longer available")
    
    ride.driver_id = current_user.get("id")
    ride.driver_name = current_user.get("name")
    ride.status = RideStatus.ACCEPTED
    ride.accepted_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "success": True,
        "message": "Ride accepted successfully"
    }

@router.put("/{ride_id}/cancel")
async def cancel_ride(
    ride_id: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a ride"""
    ride = db.query(Ride).filter(Ride.ride_id == ride_id).first()
    
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    if ride.rider_id == user_id:
        ride.status = RideStatus.CANCELLED_BY_RIDER
    elif ride.driver_id == user_id:
        ride.status = RideStatus.CANCELLED_BY_DRIVER
    elif user_role == "admin":
        ride.status = RideStatus.CANCELLED_BY_RIDER  # Use appropriate status
    else:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this ride")
    
    ride.cancelled_at = datetime.utcnow()
    ride.cancellation_reason = reason
    
    db.commit()
    
    return {
        "success": True,
        "message": "Ride cancelled successfully"
    }