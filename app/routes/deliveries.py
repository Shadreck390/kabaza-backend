from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import json
from datetime import datetime

from app.db.database import get_db
from app.auth.jwt import get_current_user

router = APIRouter()

@router.post("/book")
async def book_delivery(
    body: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Book a package delivery."""
    sender_id = current_user.get("id")
    if not sender_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Generate a unique delivery ID
    delivery_id = f"DEL{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"

    # Use the fare sent by the frontend
    fare = body.get("fare", 5000)

    try:
        db.execute(
            text("""
                INSERT INTO deliveries (
                    delivery_id, sender_id, sender_name, sender_phone,
                    recipient_name, recipient_phone, pickup_location, delivery_location,
                    package_type, package_weight, package_description,
                    requires_signature, is_fragile, insurance, fare, status
                ) VALUES (
                    :delivery_id, :sender_id, :sender_name, :sender_phone,
                    :recipient_name, :recipient_phone, :pickup_location, :delivery_location,
                    :package_type, :package_weight, :package_description,
                    :requires_signature, :is_fragile, :insurance, :fare, 'requested'
                )
            """),
            {
                "delivery_id": delivery_id,
                "sender_id": sender_id,
                "sender_name": body.get("senderName"),
                "sender_phone": body.get("senderPhone"),
                "recipient_name": body.get("recipientName"),
                "recipient_phone": body.get("recipientPhone"),
                "pickup_location": json.dumps(body.get("pickupCoordinates", {})),
                "delivery_location": json.dumps(body.get("deliveryCoordinates", {})),
                "package_type": body.get("packageType"),
                "package_weight": body.get("packageWeight"),
                "package_description": body.get("packageDescription"),
                "requires_signature": body.get("requiresSignature", False),
                "is_fragile": body.get("isFragile", False),
                "insurance": body.get("insurance", False),
                "fare": fare,
            }
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Could not save delivery: {str(e)}")

    return {"success": True, "deliveryId": delivery_id, "message": "Delivery booked successfully"}


@router.get("/history")
async def get_delivery_history(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the sender's past deliveries."""
    sender_id = current_user.get("id")
    
    results = db.execute(
        text("""
            SELECT delivery_id, recipient_name, pickup_location, delivery_location, fare, status, created_at
            FROM deliveries
            WHERE sender_id = :uid
            ORDER BY created_at DESC
        """),
        {"uid": sender_id}
    ).fetchall()

    deliveries = []
    for row in results:
        deliveries.append({
            "deliveryId": row.delivery_id,
            "recipientName": row.recipient_name,
            "pickup": json.loads(row.pickup_location) if isinstance(row.pickup_location, str) else row.pickup_location,
            "delivery": json.loads(row.delivery_location) if isinstance(row.delivery_location, str) else row.delivery_location,
            "fare": float(row.fare) if row.fare else 0,
            "status": row.status,
            "createdAt": row.created_at.isoformat() if row.created_at else None,
        })

    return {"deliveries": deliveries, "count": len(deliveries)}