from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_db
from app.auth.jwt import get_current_user
from app.models.sql_models import Ride
from app.models.rating import Rating  # We'll create this in step 2

router = APIRouter()


class RatingRequest(BaseModel):
    ride_id: int          # The database ID (not the string ride_id)
    ratee_id: int         # Driver's user ID
    stars: int            # 1-5
    comment: Optional[str] = None


@router.post("")
async def submit_rating(
    data: RatingRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a rating for a driver after a ride"""
    rater_id = current_user.get("id")
    if not rater_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # 1. Verify the ride exists and belongs to this rater
    ride = db.query(Ride).filter(Ride.id == data.ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")

    if ride.rider_id != rater_id:
        raise HTTPException(status_code=403, detail="You can only rate your own rides")

    # 2. Prevent duplicate ratings
    existing = db.query(Rating).filter(
        Rating.ride_id == data.ride_id,
        Rating.rater_id == rater_id,
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="You already rated this ride")

    # 3. Create the rating
    new_rating = Rating(
        ride_id=data.ride_id,
        rater_id=rater_id,
        ratee_id=data.ratee_id,
        stars=data.stars,
        comment=data.comment,
        created_at=datetime.utcnow(),
    )

    try:
        db.add(new_rating)
        db.commit()
        db.refresh(new_rating)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save rating: {str(e)}")

    return {
        "success": True,
        "ratingId": new_rating.id,
        "message": "Rating submitted successfully",
    }


@router.get("/driver/{driver_id}")
async def get_driver_rating(
    driver_id: int,
    db: Session = Depends(get_db),
):
    """Get a driver's average rating (public endpoint)"""
    ratings = db.query(Rating).filter(Rating.ratee_id == driver_id).all()

    if not ratings:
        return {"driver_id": driver_id, "average": 0, "total": 0, "ratings": []}

    avg = sum(r.stars for r in ratings) / len(ratings)

    return {
        "driver_id": driver_id,
        "average": round(avg, 2),
        "total": len(ratings),
        "ratings": [
            {"stars": r.stars, "comment": r.comment, "created_at": r.created_at}
            for r in ratings
        ],
    }