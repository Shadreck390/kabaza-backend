"""
Payment Routes for Kabaza
Handles TNM Mpamba, Airtel Money, wallet, and payout endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import uuid

from app.db.database import get_db
from app.auth.jwt import get_current_user
from app.services.payment_service import get_payment_service, PaymentService
from app.models.sql_models import (
    PayoutMethod, Rider, Driver, Ride, WalletTransaction,
    DriverEarning, Payout, RiderPaymentMethod
)
from app.schemas.ride import (
    MobileMoneyPaymentRequest, MobileMoneyPaymentResponse,
    PaymentStatusResponse
)
from app.schemas.user import (
    WalletTopupRequest, WalletTransactionResponse,
    WalletBalanceResponse, PaymentMethodCreate,
    PaymentMethodResponse
)
from pydantic import BaseModel, Field

router = APIRouter(prefix="/payments", tags=["Payments"])


# ============================================
# SCHEMAS
# ============================================

class PayoutRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to withdraw in MWK")
    payout_method: str = Field(..., pattern="^(tnm_mpamba|airtel_money)$")


class PayoutResponse(BaseModel):
    success: bool
    payout_id: Optional[int] = None
    reference: str
    amount: float
    fee: float
    message: str


class DriverBalanceResponse(BaseModel):
    total_earnings: float
    available_balance: float
    pending_balance: float
    total_paid_out: float
    minimum_payout: float = 5000.0
    currency: str = "MWK"


class PayoutHistoryResponse(BaseModel):
    id: int
    amount: float
    fee: float
    net_amount: float
    payout_method: str
    status: str
    reference_number: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class WalletCreditRequest(BaseModel):
    amount: float = Field(..., gt=0, allow_inf_nan=False)


class WalletPayoutRequest(BaseModel):
    amount: float = Field(..., gt=0, allow_inf_nan=False)
    method: str = Field(default="mobile_money", pattern="^(mobile_money|tnm_mpamba|airtel_money)$")


wallet_router = APIRouter()


def get_wallet_rider(current_user: dict, db: Session) -> Rider:
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Not authenticated")

    rider = db.query(Rider).filter(Rider.user_id == user_id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    return rider


def get_wallet_driver(current_user: dict, db: Session) -> Driver:
    if current_user.get("role") != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can access payouts")

    user_id = current_user.get("sub") or current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Not authenticated")

    driver = db.query(Driver).filter(Driver.user_id == user_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
    return driver


@wallet_router.get("")
async def get_wallet(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the user's wallet balance and recent transactions."""
    if current_user.get("role") == "driver":
        driver = get_wallet_driver(current_user, db)
        payouts = (
            db.query(Payout)
            .filter(Payout.driver_id == driver.id)
            .order_by(Payout.created_at.desc())
            .limit(10)
            .all()
        )
        return {
            "balance": float(driver.available_balance or 0),
            "total_earned": float(driver.total_earnings or 0),
            "pending": float(driver.pending_balance or 0),
            "currency": "MWK",
            "is_driver": True,
            "transactions": [
                {
                    "id": payout.id,
                    "type": "debit",
                    "amount": float(payout.amount),
                    "description": f"Driver payout - {payout.reference_number}",
                    "method": payout.payout_method.value,
                    "status": payout.status,
                    "timestamp": payout.created_at.isoformat() if payout.created_at else None,
                }
                for payout in payouts
            ],
        }

    rider = get_wallet_rider(current_user, db)
    transactions = (
        db.query(WalletTransaction)
        .filter(WalletTransaction.rider_id == rider.id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(10)
        .all()
    )

    transaction_list = [
        {
            "id": transaction.id,
            "type": (
                "credit"
                if transaction.transaction_type in ("deposit", "refund")
                else "debit"
            ),
            "amount": float(transaction.amount),
            "description": transaction.description or "Wallet transaction",
            "method": transaction.payment_method,
            "status": transaction.status,
            "timestamp": (
                transaction.completed_at or transaction.created_at
            ).isoformat()
            if transaction.completed_at or transaction.created_at
            else None,
            "icon": (
                "account-balance-wallet"
                if transaction.transaction_type in ("deposit", "refund")
                else "directions-car"
            ),
            "color": (
                "#10B981"
                if transaction.transaction_type in ("deposit", "refund")
                else "#EF4444"
            ),
        }
        for transaction in transactions
    ]

    return {
        "balance": float(rider.wallet_balance or 0),
        "total_earned": 0,
        "pending": 0,
        "currency": "MWK",
        "transactions": transaction_list,
    }


@wallet_router.post("/topup")
async def topup_wallet(
    body: WalletCreditRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add funds to the wallet using the development top-up flow."""
    rider = get_wallet_rider(current_user, db)
    amount = body.amount
    balance_before = float(rider.wallet_balance or 0)
    balance_after = balance_before + amount

    rider.wallet_balance = balance_after
    db.add(WalletTransaction(
        rider_id=rider.id,
        transaction_type="deposit",
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        payment_method="wallet",
        reference_type="topup",
        description="Wallet top-up",
        status="completed",
        completed_at=datetime.utcnow(),
    ))
    db.commit()

    return {"success": True, "message": f"Added MK {amount} to wallet"}


@wallet_router.get("/payouts")
async def get_wallet_payout_history(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the driver's payout history."""
    driver = get_wallet_driver(current_user, db)
    payouts = (
        db.query(Payout)
        .filter(Payout.driver_id == driver.id)
        .order_by(Payout.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "payouts": [
            {
                "id": payout.id,
                "amount": float(payout.amount),
                "fee": float(payout.fee or 0),
                "netAmount": float(payout.net_amount),
                "method": payout.payout_method.value.replace("_", " ").title(),
                "status": payout.status,
                "reference": payout.reference_number,
                "timestamp": payout.created_at.isoformat() if payout.created_at else None,
            }
            for payout in payouts
        ]
    }


@wallet_router.post("/payout")
async def request_wallet_payout(
    body: WalletPayoutRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request a withdrawal from the driver's available earnings."""
    driver = get_wallet_driver(current_user, db)
    if driver.verification_status != "verified":
        raise HTTPException(status_code=403, detail="Driver must be verified to request payout")

    amount = body.amount
    if amount < 5000:
        raise HTTPException(status_code=400, detail="Minimum withdrawal is MK 5,000")

    driver = (
        db.query(Driver)
        .filter(Driver.id == driver.id)
        .with_for_update()
        .first()
    )
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
    if float(driver.available_balance or 0) < amount:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")

    if body.method == "mobile_money":
        payout_method = driver.payout_method
    else:
        payout_method = body.method
    if isinstance(payout_method, str):
        try:
            payout_method = PayoutMethod(payout_method)
        except ValueError:
            raise HTTPException(status_code=400, detail="Unsupported payout method")
    if payout_method not in (PayoutMethod.TNM_MPAMBA, PayoutMethod.AIRTEL_MONEY):
        raise HTTPException(status_code=400, detail="Unsupported payout method")

    fee = round(max(amount * 0.01, 100))
    net_amount = amount - fee
    reference = f"PAYOUT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

    driver.available_balance -= amount
    db.add(Payout(
        driver_id=driver.id,
        amount=amount,
        fee=fee,
        net_amount=net_amount,
        payout_method=payout_method,
        status="pending",
        reference_number=reference,
        tnm_mpamba_phone=driver.tnm_mpamba_phone if payout_method == PayoutMethod.TNM_MPAMBA else None,
        airtel_money_phone=driver.airtel_money_phone if payout_method == PayoutMethod.AIRTEL_MONEY else None,
    ))
    db.commit()

    return {
        "success": True,
        "reference": reference,
        "amount": amount,
        "fee": fee,
        "net_amount": net_amount,
        "message": f"Withdrawal of MK {amount:,.0f} submitted. Net MK {net_amount:,.0f}",
    }


# ============================================
# RIDE PAYMENT ENDPOINTS
# ============================================

@router.post("/ride/request", response_model=MobileMoneyPaymentResponse)
async def request_ride_payment(
    request: MobileMoneyPaymentRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Request mobile money payment for a ride
    
    - **ride_id**: Ride ID to pay for
    - **payment_method**: tnm_mpamba or airtel_money
    - **phone_number**: Mobile money phone number
    """
    ride = db.query(Ride).filter(Ride.ride_id == request.ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    # Verify user owns this ride
    rider = db.query(Rider).filter(Rider.user_id == current_user.get("sub")).first()
    if ride.rider_id != rider.id:
        raise HTTPException(status_code=403, detail="Not authorized to pay for this ride")
    
    payment_service = get_payment_service(use_mock=True)  # Use mock for development
    
    result = await payment_service.process_ride_payment(
        db=db,
        ride=ride,
        payment_method=request.payment_method.value,
        phone=request.phone_number
    )
    
    if result.get("success"):
        return MobileMoneyPaymentResponse(
            success=True,
            message=result.get("message", "Payment request sent"),
            ride_id=request.ride_id,
            amount=ride.fare or ride.estimated_fare,
            payment_method=request.payment_method.value,
            phone_number=request.phone_number,
            transaction_id=result.get("transaction_id"),
            status=result.get("status", "pending"),
            next_step="Check your phone and enter PIN to complete payment"
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Payment request failed")
        )


@router.get("/ride/{ride_id}/status", response_model=PaymentStatusResponse)
async def check_ride_payment_status(
    ride_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check payment status for a ride
    """
    ride = db.query(Ride).filter(Ride.ride_id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    return PaymentStatusResponse(
        ride_id=ride_id,
        payment_status=ride.payment_status,
        transaction_id=ride.payment_transaction_id,
        amount=ride.fare or ride.estimated_fare,
        completed_at=ride.payment_completed_at
    )


# ============================================
# WALLET ENDPOINTS
# ============================================

@router.get("/wallet/balance", response_model=WalletBalanceResponse)
async def get_wallet_balance(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's wallet balance
    """
    rider = db.query(Rider).filter(Rider.user_id == current_user.get("sub")).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    return WalletBalanceResponse(
        balance=rider.wallet_balance,
        total_spent=rider.total_spent,
        total_saved=0.0,  # Calculate from promos
        referral_credits=rider.referral_credits
    )


@router.post("/wallet/topup")
async def topup_wallet(
    request: WalletTopupRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Top up wallet via mobile money
    """
    rider = db.query(Rider).filter(Rider.user_id == current_user.get("sub")).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    payment_service = get_payment_service(use_mock=True)
    
    result = await payment_service.topup_wallet(
        db=db,
        rider_id=rider.id,
        amount=request.amount,
        payment_method=request.payment_method,
        phone=request.phone_number
    )
    
    if result.get("success"):
        return {
            "success": True,
            "message": "Top-up initiated. Check your phone.",
            "amount": request.amount,
            "reference": result.get("reference")
        }
    else:
        raise HTTPException(status_code=400, detail=result.get("message"))


@router.get("/wallet/transactions", response_model=List[WalletTransactionResponse])
async def get_wallet_transactions(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get wallet transaction history
    """
    rider = db.query(Rider).filter(Rider.user_id == current_user.get("sub")).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    transactions = db.query(WalletTransaction).filter(
        WalletTransaction.rider_id == rider.id
    ).order_by(WalletTransaction.created_at.desc()).limit(limit).all()
    
    return transactions


# ============================================
# PAYMENT METHODS ENDPOINTS
# ============================================

@router.get("/methods", response_model=List[PaymentMethodResponse])
async def get_payment_methods(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get saved payment methods
    """
    rider = db.query(Rider).filter(Rider.user_id == current_user.get("sub")).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    methods = db.query(RiderPaymentMethod).filter(
        RiderPaymentMethod.rider_id == rider.id
    ).all()
    
    result = []
    for method in methods:
        result.append(PaymentMethodResponse(
            id=method.id,
            method_type=method.method_type,
            display_name=method.display_name if hasattr(method, 'display_name') else method.method_type,
            phone_number=method.tnm_mpamba_phone or method.airtel_money_phone,
            is_default=method.is_default,
            is_verified=method.is_verified,
            last_used_at=method.last_used_at
        ))
    
    return result


@router.post("/methods", response_model=PaymentMethodResponse)
async def add_payment_method(
    request: PaymentMethodCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a new payment method
    """
    rider = db.query(Rider).filter(Rider.user_id == current_user.get("sub")).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    # If setting as default, unset other defaults
    if request.is_default:
        db.query(RiderPaymentMethod).filter(
            RiderPaymentMethod.rider_id == rider.id
        ).update({"is_default": False})
    
    method = RiderPaymentMethod(
        rider_id=rider.id,
        method_type=request.method_type,
        is_default=request.is_default
    )
    
    if request.method_type == "tnm_mpamba":
        method.tnm_mpamba_phone = request.phone
        method.tnm_mpamba_nickname = request.nickname
    elif request.method_type == "airtel_money":
        method.airtel_money_phone = request.phone
        method.airtel_money_nickname = request.nickname
    
    db.add(method)
    db.commit()
    db.refresh(method)
    
    return PaymentMethodResponse(
        id=method.id,
        method_type=method.method_type,
        display_name=request.nickname or request.method_type,
        phone_number=request.phone,
        is_default=method.is_default,
        is_verified=method.is_verified,
        last_used_at=None
    )


@router.delete("/methods/{method_id}")
async def delete_payment_method(
    method_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a payment method
    """
    rider = db.query(Rider).filter(Rider.user_id == current_user.get("sub")).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    method = db.query(RiderPaymentMethod).filter(
        RiderPaymentMethod.id == method_id,
        RiderPaymentMethod.rider_id == rider.id
    ).first()
    
    if not method:
        raise HTTPException(status_code=404, detail="Payment method not found")
    
    db.delete(method)
    db.commit()
    
    return {"success": True, "message": "Payment method deleted"}


# ============================================
# DRIVER EARNINGS ENDPOINTS
# ============================================

@router.get("/driver/balance", response_model=DriverBalanceResponse)
async def get_driver_balance(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get driver earnings balance
    """
    driver = db.query(Driver).filter(Driver.user_id == current_user.get("sub")).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
    
    return DriverBalanceResponse(
        total_earnings=driver.total_earnings,
        available_balance=driver.available_balance,
        pending_balance=driver.pending_balance,
        total_paid_out=driver.total_paid_out
    )


@router.get("/driver/earnings")
async def get_driver_earnings(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get driver earnings history
    """
    driver = db.query(Driver).filter(Driver.user_id == current_user.get("sub")).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
    
    earnings = db.query(DriverEarning).filter(
        DriverEarning.driver_id == driver.id
    ).order_by(DriverEarning.created_at.desc()).limit(limit).all()
    
    return earnings


# ============================================
# PAYOUT ENDPOINTS
# ============================================

@router.post("/driver/payout", response_model=PayoutResponse)
async def request_payout(
    request: PayoutRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Request payout to mobile money
    """
    driver = db.query(Driver).filter(Driver.user_id == current_user.get("sub")).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
    
    if driver.verification_status != "verified":
        raise HTTPException(status_code=400, detail="Driver must be verified to request payout")
    
    payment_service = get_payment_service(use_mock=True)
    
    result = await payment_service.process_payout(
        db=db,
        driver_id=driver.id,
        amount=request.amount,
        payout_method=request.payout_method
    )
    
    if result.get("success"):
        return PayoutResponse(**result)
    else:
        raise HTTPException(status_code=400, detail=result.get("message"))


@router.get("/driver/payouts", response_model=List[PayoutHistoryResponse])
async def get_payout_history(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get driver payout history
    """
    driver = db.query(Driver).filter(Driver.user_id == current_user.get("sub")).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
    
    payouts = db.query(Payout).filter(
        Payout.driver_id == driver.id
    ).order_by(Payout.created_at.desc()).limit(limit).all()
    
    return payouts


# ============================================
# CALLBACK ENDPOINTS (For Mobile Money Providers)
# ============================================

@router.post("/tnm/callback")
async def tnm_mpamba_callback(
    request: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Callback endpoint for TNM Mpamba payment notifications
    """
    transaction_id = request.get("transaction_id")
    status = request.get("status")
    reference = request.get("reference")
    
    # Process in background
    background_tasks.add_task(process_tnm_callback, db, transaction_id, status, reference)
    
    return {"status": "received"}


@router.post("/airtel/callback")
async def airtel_money_callback(
    request: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Callback endpoint for Airtel Money payment notifications
    """
    transaction_id = request.get("transaction", {}).get("id")
    status = request.get("transaction", {}).get("status")
    reference = request.get("transaction", {}).get("reference")
    
    # Process in background
    background_tasks.add_task(process_airtel_callback, db, transaction_id, status, reference)
    
    return {"status": "received"}


async def process_tnm_callback(db: Session, transaction_id: str, status: str, reference: str):
    """Process TNM callback"""
    # Find ride or transaction by reference
    ride = db.query(Ride).filter(Ride.payment_reference == reference).first()
    if ride:
        if status == "SUCCESS":
            ride.payment_status = "completed"
            ride.payment_completed_at = datetime.utcnow()
            ride.tnm_mpamba_status = "completed"
        else:
            ride.payment_status = "failed"
            ride.tnm_mpamba_status = "failed"
        db.commit()


async def process_airtel_callback(db: Session, transaction_id: str, status: str, reference: str):
    """Process Airtel callback"""
    ride = db.query(Ride).filter(Ride.payment_reference == reference).first()
    if ride:
        if status == "SUCCESS":
            ride.payment_status = "completed"
            ride.payment_completed_at = datetime.utcnow()
            ride.airtel_money_status = "completed"
        else:
            ride.payment_status = "failed"
            ride.airtel_money_status = "failed"
        db.commit()