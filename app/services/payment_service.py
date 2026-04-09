"""
Payment Service for Kabaza
Handles TNM Mpamba and Airtel Money payments in Malawi
Includes wallet management, payouts, and transaction tracking
"""

import httpx
import json
import uuid
import hashlib
import hmac
import time
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from decimal import Decimal

from app.models.sql_models import (
    Rider, Driver, Ride, WalletTransaction,
    DriverEarning, Payout, RiderPaymentMethod
)
from app.schemas.ride import PaymentStatusEnum

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURATION
# ============================================

class PaymentConfig:
    """Payment configuration for mobile money providers"""
    
    # TNM Mpamba Configuration
    TNM_MPAMBA_API_KEY = "your_tnm_api_key"  # Get from TNM
    TNM_MPAMBA_API_SECRET = "your_tnm_api_secret"
    TNM_MPAMBA_BASE_URL = "https://api.tnm.co.mw/mpamba/v1"  # Production
    TNM_MPAMBA_SANDBOX_URL = "https://sandbox.tnm.co.mw/mpamba/v1"  # Sandbox
    
    # Airtel Money Configuration
    AIRTEL_API_KEY = "your_airtel_api_key"  # Get from Airtel
    AIRTEL_API_SECRET = "your_airtel_api_secret"
    AIRTEL_BASE_URL = "https://api.airtel.com/money/v1"  # Production
    AIRTEL_SANDBOX_URL = "https://sandbox.airtel.com/money/v1"  # Sandbox
    
    # Platform Settings
    PLATFORM_FEE_PERCENT = 15.0  # 15% commission
    MINIMUM_PAYOUT_AMOUNT = 5000.0  # Minimum 5,000 MWK for payout
    PAYOUT_PROCESSING_FEE = 100.0  # 100 MWK payout fee
    TRANSACTION_TIMEOUT_SECONDS = 120  # 2 minutes timeout
    MAX_RETRY_ATTEMPTS = 3
    
    # Use sandbox for development
    USE_SANDBOX = True
    
    @classmethod
    def get_tnm_url(cls):
        return cls.TNM_MPAMBA_SANDBOX_URL if cls.USE_SANDBOX else cls.TNM_MPAMBA_BASE_URL
    
    @classmethod
    def get_airtel_url(cls):
        return cls.AIRTEL_SANDBOX_URL if cls.USE_SANDBOX else cls.AIRTEL_BASE_URL


# ============================================
# BASE MOBILE MONEY PROVIDER
# ============================================

class MobileMoneyProvider:
    """Base class for mobile money providers"""
    
    def __init__(self):
        self.timeout = PaymentConfig.TRANSACTION_TIMEOUT_SECONDS
    
    def generate_reference(self, prefix: str) -> str:
        """Generate unique transaction reference"""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"{prefix}-{timestamp}-{unique_id}"
    
    def format_phone(self, phone: str) -> str:
        """Format phone number to required format"""
        cleaned = ''.join(c for c in phone if c.isdigit())
        if cleaned.startswith('265'):
            return cleaned
        elif cleaned.startswith('0'):
            return '265' + cleaned[1:]
        return '265' + cleaned
    
    def calculate_hash(self, data: str, secret: str) -> str:
        """Calculate HMAC hash for request signing"""
        return hmac.new(
            secret.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()


# ============================================
# TNM MPAMBA PROVIDER
# ============================================

class TNMMpambaProvider(MobileMoneyProvider):
    """TNM Mpamba payment integration"""
    
    def __init__(self):
        super().__init__()
        self.api_key = PaymentConfig.TNM_MPAMBA_API_KEY
        self.api_secret = PaymentConfig.TNM_MPAMBA_API_SECRET
        self.base_url = PaymentConfig.get_tnm_url()
    
    async def request_payment(
        self,
        phone: str,
        amount: float,
        reference: str,
        description: str = "Kabaza Ride Payment"
    ) -> Dict[str, Any]:
        """
        Request payment from TNM Mpamba user
        
        Args:
            phone: Customer phone number
            amount: Amount in MWK
            reference: Unique transaction reference
            description: Payment description
            
        Returns:
            Transaction response with status
        """
        formatted_phone = self.format_phone(phone)
        
        payload = {
            "msisdn": formatted_phone,
            "amount": str(int(amount)),
            "reference": reference,
            "description": description,
            "currency": "MWK",
            "callback_url": f"https://api.kabaza.com/api/payments/tnm/callback"
        }
        
        # Generate signature
        signature_data = f"{formatted_phone}{int(amount)}{reference}"
        signature = self.calculate_hash(signature_data, self.api_secret)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Signature": signature,
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/payments/request",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "transaction_id": data.get("transaction_id"),
                        "reference": reference,
                        "status": "pending",
                        "message": "Payment request sent. Check phone for USSD prompt."
                    }
                else:
                    logger.error(f"TNM payment failed: {response.text}")
                    return {
                        "success": False,
                        "message": f"Payment failed: {response.text}",
                        "status": "failed"
                    }
                    
        except Exception as e:
            logger.error(f"TNM payment error: {str(e)}")
            return {
                "success": False,
                "message": "Unable to process payment. Please try again.",
                "status": "error"
            }
    
    async def check_status(self, transaction_id: str) -> Dict[str, Any]:
        """Check payment status"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/payments/{transaction_id}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status_map = {
                        "SUCCESS": "completed",
                        "PENDING": "pending",
                        "FAILED": "failed",
                        "EXPIRED": "failed"
                    }
                    
                    return {
                        "success": True,
                        "status": status_map.get(data.get("status"), "pending"),
                        "transaction_id": transaction_id,
                        "amount": float(data.get("amount", 0)),
                        "completed_at": data.get("completed_at")
                    }
                else:
                    return {
                        "success": False,
                        "status": "unknown",
                        "message": "Could not check status"
                    }
                    
        except Exception as e:
            logger.error(f"Status check error: {str(e)}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }
    
    async def send_payout(
        self,
        phone: str,
        amount: float,
        reference: str,
        recipient_name: str
    ) -> Dict[str, Any]:
        """
        Send money to driver via TNM Mpamba
        
        Args:
            phone: Driver's TNM Mpamba number
            amount: Amount to send
            reference: Unique reference
            recipient_name: Name of recipient
            
        Returns:
            Payout response
        """
        formatted_phone = self.format_phone(phone)
        net_amount = amount - PaymentConfig.PAYOUT_PROCESSING_FEE
        
        payload = {
            "msisdn": formatted_phone,
            "amount": str(int(net_amount)),
            "reference": reference,
            "recipient_name": recipient_name,
            "narration": f"Kabaza Earnings Payout - {reference}",
            "currency": "MWK"
        }
        
        signature_data = f"{formatted_phone}{int(net_amount)}{reference}"
        signature = self.calculate_hash(signature_data, self.api_secret)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Signature": signature,
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/disbursements/send",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "transaction_id": data.get("transaction_id"),
                        "reference": reference,
                        "amount": net_amount,
                        "fee": PaymentConfig.PAYOUT_PROCESSING_FEE,
                        "status": "processing"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Payout failed: {response.text}",
                        "status": "failed"
                    }
                    
        except Exception as e:
            logger.error(f"TNM payout error: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "status": "error"
            }


# ============================================
# AIRTEL MONEY PROVIDER
# ============================================

class AirtelMoneyProvider(MobileMoneyProvider):
    """Airtel Money payment integration"""
    
    def __init__(self):
        super().__init__()
        self.api_key = PaymentConfig.AIRTEL_API_KEY
        self.api_secret = PaymentConfig.AIRTEL_API_SECRET
        self.base_url = PaymentConfig.get_airtel_url()
    
    async def request_payment(
        self,
        phone: str,
        amount: float,
        reference: str,
        description: str = "Kabaza Ride Payment"
    ) -> Dict[str, Any]:
        """
        Request payment from Airtel Money user
        """
        formatted_phone = self.format_phone(phone)
        
        payload = {
            "msisdn": formatted_phone,
            "amount": str(int(amount)),
            "reference": reference,
            "description": description,
            "currency": "MWK",
            "callback_url": f"https://api.kabaza.com/api/payments/airtel/callback"
        }
        
        # Airtel uses Bearer token authentication
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Country": "MW",
            "X-Currency": "MWK",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/merchant/v1/payments",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    return {
                        "success": True,
                        "transaction_id": data.get("transaction", {}).get("id"),
                        "reference": reference,
                        "status": "pending",
                        "message": "Payment request sent. Check your phone."
                    }
                else:
                    logger.error(f"Airtel payment failed: {response.text}")
                    return {
                        "success": False,
                        "message": f"Payment failed: {response.text}",
                        "status": "failed"
                    }
                    
        except Exception as e:
            logger.error(f"Airtel payment error: {str(e)}")
            return {
                "success": False,
                "message": "Unable to process payment. Please try again.",
                "status": "error"
            }
    
    async def check_status(self, transaction_id: str) -> Dict[str, Any]:
        """Check Airtel payment status"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Country": "MW",
            "X-Currency": "MWK"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/merchant/v1/payments/{transaction_id}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    transaction = data.get("transaction", {})
                    status_map = {
                        "SUCCESS": "completed",
                        "PENDING": "pending",
                        "FAILED": "failed",
                        "CANCELLED": "failed"
                    }
                    
                    return {
                        "success": True,
                        "status": status_map.get(transaction.get("status"), "pending"),
                        "transaction_id": transaction_id,
                        "amount": float(transaction.get("amount", 0)),
                        "completed_at": transaction.get("updated_at")
                    }
                else:
                    return {
                        "success": False,
                        "status": "unknown",
                        "message": "Could not check status"
                    }
                    
        except Exception as e:
            logger.error(f"Status check error: {str(e)}")
            return {
                "success": False,
                "status": "error",
                "message": str(e)
            }
    
    async def send_payout(
        self,
        phone: str,
        amount: float,
        reference: str,
        recipient_name: str
    ) -> Dict[str, Any]:
        """
        Send money to driver via Airtel Money
        """
        formatted_phone = self.format_phone(phone)
        net_amount = amount - PaymentConfig.PAYOUT_PROCESSING_FEE
        
        payload = {
            "msisdn": formatted_phone,
            "amount": str(int(net_amount)),
            "reference": reference,
            "recipient": {
                "name": recipient_name,
                "type": "individual"
            },
            "narration": f"Kabaza Earnings - {reference}"
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Country": "MW",
            "X-Currency": "MWK",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/disbursement/v1/send",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    return {
                        "success": True,
                        "transaction_id": data.get("disbursement", {}).get("id"),
                        "reference": reference,
                        "amount": net_amount,
                        "fee": PaymentConfig.PAYOUT_PROCESSING_FEE,
                        "status": "processing"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Payout failed: {response.text}",
                        "status": "failed"
                    }
                    
        except Exception as e:
            logger.error(f"Airtel payout error: {str(e)}")
            return {
                "success": False,
                "message": str(e),
                "status": "error"
            }


# ============================================
# PAYMENT SERVICE
# ============================================

class PaymentService:
    """Main payment service orchestrator"""
    
    def __init__(self):
        self.tnm = TNMMpambaProvider()
        self.airtel = AirtelMoneyProvider()
    
    def get_provider(self, method: str):
        """Get appropriate payment provider"""
        if method == "tnm_mpamba":
            return self.tnm
        elif method == "airtel_money":
            return self.airtel
        else:
            raise ValueError(f"Unsupported payment method: {method}")
    
    async def process_ride_payment(
        self,
        db: Session,
        ride: Ride,
        payment_method: str,
        phone: str
    ) -> Dict[str, Any]:
        """
        Process payment for a ride
        
        Args:
            db: Database session
            ride: Ride object
            payment_method: tnm_mpamba or airtel_money
            phone: Customer phone number
            
        Returns:
            Payment result
        """
        provider = self.get_provider(payment_method)
        reference = provider.generate_reference("RIDE")
        
        # Update ride with payment info
        ride.payment_method = payment_method
        ride.payment_phone = phone
        ride.payment_reference = reference
        ride.payment_status = PaymentStatusEnum.PENDING.value
        
        # Calculate final amount
        total_amount = ride.fare if ride.fare else ride.estimated_fare
        
        # Process payment
        result = await provider.request_payment(
            phone=phone,
            amount=total_amount,
            reference=reference,
            description=f"Kabaza Ride {ride.ride_id}"
        )
        
        if result.get("success"):
            ride.payment_transaction_id = result.get("transaction_id")
            
            if payment_method == "tnm_mpamba":
                ride.tnm_mpamba_transaction_id = result.get("transaction_id")
                ride.tnm_mpamba_status = "pending"
            else:
                ride.airtel_money_transaction_id = result.get("transaction_id")
                ride.airtel_money_status = "pending"
            
            db.commit()
        
        return result
    
    async def verify_payment(
        self,
        db: Session,
        ride: Ride
    ) -> Dict[str, Any]:
        """
        Verify payment status and update ride
        
        Args:
            db: Database session
            ride: Ride object
            
        Returns:
            Verification result
        """
        provider = self.get_provider(ride.payment_method)
        transaction_id = ride.payment_transaction_id
        
        if not transaction_id:
            return {
                "success": False,
                "message": "No transaction ID found"
            }
        
        result = await provider.check_status(transaction_id)
        
        if result.get("success"):
            status = result.get("status")
            
            if status == "completed":
                ride.payment_status = PaymentStatusEnum.COMPLETED.value
                ride.payment_completed_at = datetime.utcnow()
                
                if ride.payment_method == "tnm_mpamba":
                    ride.tnm_mpamba_status = "completed"
                else:
                    ride.airtel_money_status = "completed"
                
                # Create driver earning record
                await self._create_driver_earning(db, ride)
                
            elif status == "failed":
                ride.payment_status = PaymentStatusEnum.FAILED.value
                
                if ride.payment_method == "tnm_mpamba":
                    ride.tnm_mpamba_status = "failed"
                else:
                    ride.airtel_money_status = "failed"
            
            db.commit()
        
        return result
    
    async def _create_driver_earning(self, db: Session, ride: Ride):
        """Create driver earning record after successful payment"""
        if ride.driver_id:
            platform_fee = ride.platform_fee or (ride.fare * PaymentConfig.PLATFORM_FEE_PERCENT / 100)
            driver_earning = ride.fare - platform_fee + (ride.tip_amount or 0)
            
            earning = DriverEarning(
                driver_id=ride.driver_id,
                ride_id=ride.id,
                ride_fare=ride.fare,
                platform_fee=platform_fee,
                driver_earning=driver_earning,
                tip_amount=ride.tip_amount or 0,
                status="pending",
                rider_payment_method=ride.payment_method,
                rider_payment_reference=ride.payment_transaction_id
            )
            db.add(earning)
            
            # Update driver balance
            driver = db.query(Driver).filter(Driver.id == ride.driver_id).first()
            if driver:
                driver.pending_balance += driver_earning
                driver.total_earnings += driver_earning
            
            db.commit()
    
    async def process_payout(
        self,
        db: Session,
        driver_id: int,
        amount: float,
        payout_method: str
    ) -> Dict[str, Any]:
        """
        Process payout to driver
        
        Args:
            db: Database session
            driver_id: Driver ID
            amount: Amount to payout
            payout_method: tnm_mpamba or airtel_money
            
        Returns:
            Payout result
        """
        driver = db.query(Driver).filter(Driver.id == driver_id).first()
        if not driver:
            return {"success": False, "message": "Driver not found"}
        
        if driver.available_balance < amount:
            return {"success": False, "message": "Insufficient available balance"}
        
        if amount < PaymentConfig.MINIMUM_PAYOUT_AMOUNT:
            return {
                "success": False,
                "message": f"Minimum payout is {PaymentConfig.MINIMUM_PAYOUT_AMOUNT} MWK"
            }
        
        provider = self.get_provider(payout_method)
        reference = provider.generate_reference("PAYOUT")
        
        # Get phone number
        phone = (driver.tnm_mpamba_phone if payout_method == "tnm_mpamba" 
                 else driver.airtel_money_phone)
        
        if not phone:
            phone = driver.phone
        
        # Create payout record
        payout = Payout(
            driver_id=driver_id,
            amount=amount,
            fee=PaymentConfig.PAYOUT_PROCESSING_FEE,
            net_amount=amount - PaymentConfig.PAYOUT_PROCESSING_FEE,
            payout_method=payout_method,
            reference_number=reference,
            status="pending"
        )
        
        if payout_method == "tnm_mpamba":
            payout.tnm_mpamba_phone = phone
        else:
            payout.airtel_money_phone = phone
        
        db.add(payout)
        
        # Send payout
        result = await provider.send_payout(
            phone=phone,
            amount=amount,
            reference=reference,
            recipient_name=driver.full_name or "Driver"
        )
        
        if result.get("success"):
            payout.status = "processing"
            
            if payout_method == "tnm_mpamba":
                payout.tnm_mpamba_transaction_id = result.get("transaction_id")
            else:
                payout.airtel_money_transaction_id = result.get("transaction_id")
            
            # Deduct from driver balance
            driver.available_balance -= amount
            driver.pending_balance = max(0, driver.pending_balance - amount)
            
            db.commit()
            
            return {
                "success": True,
                "payout_id": payout.id,
                "reference": reference,
                "amount": result.get("amount"),
                "fee": result.get("fee"),
                "message": "Payout initiated successfully"
            }
        else:
            payout.status = "failed"
            payout.failure_reason = result.get("message")
            db.commit()
            
            return {
                "success": False,
                "message": result.get("message", "Payout failed")
            }
    
    async def topup_wallet(
        self,
        db: Session,
        rider_id: int,
        amount: float,
        payment_method: str,
        phone: str
    ) -> Dict[str, Any]:
        """
        Top up rider wallet via mobile money
        """
        rider = db.query(Rider).filter(Rider.id == rider_id).first()
        if not rider:
            return {"success": False, "message": "Rider not found"}
        
        provider = self.get_provider(payment_method)
        reference = provider.generate_reference("TOPUP")
        
        # Create wallet transaction
        transaction = WalletTransaction(
            rider_id=rider_id,
            transaction_type="deposit",
            amount=amount,
            balance_before=rider.wallet_balance,
            balance_after=rider.wallet_balance,  # Will update after payment
            payment_method=payment_method,
            reference_type="topup",
            description=f"Wallet top-up via {payment_method}",
            status="pending"
        )
        db.add(transaction)
        
        # Process payment
        result = await provider.request_payment(
            phone=phone,
            amount=amount,
            reference=reference,
            description="Kabaza Wallet Top-up"
        )
        
        if result.get("success"):
            transaction.payment_reference = reference
            transaction.status = "processing"
            
            if payment_method == "tnm_mpamba":
                transaction.tnm_mpamba_transaction_id = result.get("transaction_id")
            else:
                transaction.airtel_money_transaction_id = result.get("transaction_id")
            
            db.commit()
        
        return result
    
    async def verify_topup(
        self,
        db: Session,
        transaction: WalletTransaction
    ) -> Dict[str, Any]:
        """
        Verify wallet top-up and credit rider
        """
        provider = self.get_provider(transaction.payment_method)
        transaction_id = (
            transaction.tnm_mpamba_transaction_id or 
            transaction.airtel_money_transaction_id
        )
        
        result = await provider.check_status(transaction_id)
        
        if result.get("success") and result.get("status") == "completed":
            rider = db.query(Rider).filter(Rider.id == transaction.rider_id).first()
            
            transaction.status = "completed"
            transaction.completed_at = datetime.utcnow()
            transaction.balance_after = rider.wallet_balance + transaction.amount
            
            rider.wallet_balance += transaction.amount
            
            db.commit()
        
        return result


# ============================================
# SIMULATION MODE (For Development)
# ============================================

class MockPaymentService:
    """
    Mock payment service for development/testing
    Simulates TNM Mpamba and Airtel Money without actual API calls
    """
    
    def __init__(self):
        self.mock_transactions = {}
    
    async def process_ride_payment(
        self,
        db: Session,
        ride: Ride,
        payment_method: str,
        phone: str
    ) -> Dict[str, Any]:
        """Simulate ride payment"""
        reference = f"MOCK-{uuid.uuid4().hex[:8].upper()}"
        transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        
        # Simulate 90% success rate
        import random
        success = random.random() > 0.1
        
        if success:
            ride.payment_method = payment_method
            ride.payment_phone = phone
            ride.payment_reference = reference
            ride.payment_transaction_id = transaction_id
            ride.payment_status = PaymentStatusEnum.COMPLETED.value
            ride.payment_completed_at = datetime.utcnow()
            
            db.commit()
            
            # Auto-create earnings for testing
            await self._create_mock_earning(db, ride)
            
            return {
                "success": True,
                "transaction_id": transaction_id,
                "reference": reference,
                "status": "completed",
                "message": "Mock payment successful"
            }
        else:
            return {
                "success": False,
                "message": "Mock payment failed (simulated error)",
                "status": "failed"
            }
    
    async def _create_mock_earning(self, db: Session, ride: Ride):
        """Create mock driver earning"""
        if ride.driver_id:
            platform_fee = ride.fare * 0.15
            driver_earning = ride.fare - platform_fee
            
            earning = DriverEarning(
                driver_id=ride.driver_id,
                ride_id=ride.id,
                ride_fare=ride.fare,
                platform_fee=platform_fee,
                driver_earning=driver_earning,
                status="cleared",
                cleared_at=datetime.utcnow()
            )
            db.add(earning)
            
            driver = db.query(Driver).filter(Driver.id == ride.driver_id).first()
            if driver:
                driver.available_balance += driver_earning
                driver.total_earnings += driver_earning
            
            db.commit()
    
    async def process_payout(
        self,
        db: Session,
        driver_id: int,
        amount: float,
        payout_method: str
    ) -> Dict[str, Any]:
        """Simulate driver payout"""
        reference = f"PAYOUT-MOCK-{uuid.uuid4().hex[:8].upper()}"
        transaction_id = f"DISB-{uuid.uuid4().hex[:12].upper()}"
        
        driver = db.query(Driver).filter(Driver.id == driver_id).first()
        
        payout = Payout(
            driver_id=driver_id,
            amount=amount,
            fee=100.0,
            net_amount=amount - 100.0,
            payout_method=payout_method,
            reference_number=reference,
            status="completed",
            completed_at=datetime.utcnow()
        )
        
        if payout_method == "tnm_mpamba":
            payout.tnm_mpamba_transaction_id = transaction_id
            payout.tnm_mpamba_status = "completed"
        else:
            payout.airtel_money_transaction_id = transaction_id
            payout.airtel_money_status = "completed"
        
        db.add(payout)
        
        driver.available_balance -= amount
        driver.total_paid_out += (amount - 100.0)
        
        db.commit()
        
        return {
            "success": True,
            "payout_id": payout.id,
            "reference": reference,
            "amount": amount - 100.0,
            "fee": 100.0,
            "message": "Mock payout successful"
        }


# ============================================
# SERVICE FACTORY
# ============================================

def get_payment_service(use_mock: bool = True) -> PaymentService:
    """
    Get payment service instance
    
    Args:
        use_mock: Use mock service for development
        
    Returns:
        PaymentService or MockPaymentService
    """
    if use_mock:
        return MockPaymentService()
    return PaymentService()