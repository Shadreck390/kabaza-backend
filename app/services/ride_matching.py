"""
Ride Matching Service for Kabaza
Handles driver matching, fare calculation, and ETA estimation
Optimized for Malawi market with Kabaza (motorcycle) pricing
"""

import math
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import random
import logging

from app.models.sql_models import Driver, Ride, VehicleType
from app.schemas.ride import Location, RideEstimateResponse

logger = logging.getLogger(__name__)


# ============================================
# FARE CALCULATION (Malawi Market Rates)
# ============================================

class FareCalculator:
    """
    Fare calculator for Kabaza rides in Malawi
    
    Standard Rates (in MWK):
    - Motorcycle (Kabaza): 
        Base fare: 500 MWK
        Per km: 200 MWK
        Per minute: 50 MWK
        Minimum fare: 800 MWK
    
    - Car (Taxi):
        Base fare: 1000 MWK
        Per km: 400 MWK
        Per minute: 100 MWK
        Minimum fare: 1500 MWK
    
    - Bicycle:
        Base fare: 300 MWK
        Per km: 100 MWK
        Per minute: 30 MWK
        Minimum fare: 500 MWK
    """
    
    # Fare rates by vehicle type (all in MWK)
    RATES = {
        VehicleType.MOTORCYCLE.value: {
            "base_fare": 500.0,
            "per_km": 200.0,
            "per_minute": 50.0,
            "minimum_fare": 800.0,
            "platform_fee_percent": 15.0,  # 15% commission
        },
        VehicleType.CAR.value: {
            "base_fare": 1000.0,
            "per_km": 400.0,
            "per_minute": 100.0,
            "minimum_fare": 1500.0,
            "platform_fee_percent": 15.0,
        },
        VehicleType.BICYCLE.value: {
            "base_fare": 300.0,
            "per_km": 100.0,
            "per_minute": 30.0,
            "minimum_fare": 500.0,
            "platform_fee_percent": 10.0,  # Lower commission for bicycles
        },
        VehicleType.MINIBUS.value: {
            "base_fare": 2000.0,
            "per_km": 600.0,
            "per_minute": 150.0,
            "minimum_fare": 3000.0,
            "platform_fee_percent": 15.0,
        },
        VehicleType.TRUCK.value: {
            "base_fare": 3000.0,
            "per_km": 800.0,
            "per_minute": 200.0,
            "minimum_fare": 5000.0,
            "platform_fee_percent": 15.0,
        },
    }
    
    # Surge multipliers (based on demand)
    SURGE_LEVELS = {
        0: 1.0,    # Normal
        1: 1.2,    # Slight demand
        2: 1.5,    # Moderate demand
        3: 1.8,    # High demand
        4: 2.0,    # Very high demand
        5: 2.5,    # Extreme demand (peak hours/events)
    }
    
    @classmethod
    def calculate_distance(cls, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points using Haversine formula
        
        Args:
            lat1, lon1: Starting coordinates
            lat2, lon2: Ending coordinates
            
        Returns:
            Distance in kilometers
        """
        R = 6371  # Earth's radius in kilometers
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        distance = R * c
        return round(distance, 2)
    
    @classmethod
    def estimate_duration(cls, distance_km: float, vehicle_type: str) -> int:
        """
        Estimate trip duration based on distance and vehicle type
        
        Args:
            distance_km: Distance in kilometers
            vehicle_type: Type of vehicle
            
        Returns:
            Estimated duration in minutes
        """
        # Average speeds in km/h for Malawi conditions
        avg_speeds = {
            VehicleType.MOTORCYCLE.value: 25,  # Kabaza can navigate traffic
            VehicleType.CAR.value: 20,          # Cars stuck in Lilongwe/Blantyre traffic
            VehicleType.BICYCLE.value: 12,      # Slower but can use paths
            VehicleType.MINIBUS.value: 18,      # Frequent stops
            VehicleType.TRUCK.value: 15,        # Slower, careful driving
        }
        
        speed = avg_speeds.get(vehicle_type, 20)
        
        # Base time calculation
        time_hours = distance_km / speed
        time_minutes = time_hours * 60
        
        # Add buffer for traffic, pickup, dropoff
        buffer_minutes = 5 if vehicle_type == VehicleType.MOTORCYCLE.value else 8
        
        total_minutes = int(time_minutes + buffer_minutes)
        
        # Minimum duration
        return max(total_minutes, 5)
    
    @classmethod
    def get_surge_multiplier(cls, hour: int, day_of_week: int) -> float:
        """
        Calculate surge pricing based on time and demand
        
        Args:
            hour: Current hour (0-23)
            day_of_week: 0=Monday, 6=Sunday
            
        Returns:
            Surge multiplier
        """
        # Peak hours in Malawi
        morning_peak = 7 <= hour <= 9      # 7-9 AM
        evening_peak = 16 <= hour <= 19    # 4-7 PM
        night_time = 22 <= hour or hour <= 5  # 10 PM - 5 AM
        
        # Weekend
        is_weekend = day_of_week >= 5  # Saturday, Sunday
        
        if morning_peak or evening_peak:
            if is_weekend:
                return cls.SURGE_LEVELS[2]  # 1.5x
            return cls.SURGE_LEVELS[3]  # 1.8x on weekdays
        elif night_time:
            return cls.SURGE_LEVELS[2]  # 1.5x (safety premium)
        elif is_weekend:
            return cls.SURGE_LEVELS[1]  # 1.2x
        
        return cls.SURGE_LEVELS[0]  # 1.0x normal
    
    @classmethod
    def calculate_fare(
        cls,
        distance_km: float,
        duration_minutes: int,
        vehicle_type: str,
        include_surge: bool = True,
        promo_discount: float = 0.0
    ) -> Dict[str, Any]:
        """
        Calculate complete fare breakdown
        
        Args:
            distance_km: Trip distance in kilometers
            duration_minutes: Estimated duration in minutes
            vehicle_type: Type of vehicle
            include_surge: Whether to apply surge pricing
            promo_discount: Discount amount to subtract
            
        Returns:
            Dictionary with fare breakdown
        """
        rates = cls.RATES.get(vehicle_type, cls.RATES[VehicleType.MOTORCYCLE.value])
        
        # Calculate components
        distance_fare = distance_km * rates["per_km"]
        time_fare = duration_minutes * rates["per_minute"]
        
        base_total = rates["base_fare"] + distance_fare + time_fare
        
        # Apply minimum fare
        base_total = max(base_total, rates["minimum_fare"])
        
        # Round to nearest 50 MWK (common practice in Malawi)
        base_total = round(base_total / 50) * 50
        
        # Apply surge if enabled
        surge_multiplier = 1.0
        if include_surge:
            now = datetime.utcnow()
            surge_multiplier = cls.get_surge_multiplier(now.hour, now.weekday())
        
        subtotal = base_total * surge_multiplier
        
        # Apply promo discount
        discount_applied = min(promo_discount, subtotal)
        after_discount = subtotal - discount_applied
        
        # Calculate platform fee
        platform_fee = after_discount * (rates["platform_fee_percent"] / 100)
        platform_fee = round(platform_fee / 10) * 10  # Round to nearest 10
        
        # Final total
        total_fare = after_discount
        driver_earning = total_fare - platform_fee
        
        return {
            "distance_km": distance_km,
            "duration_minutes": duration_minutes,
            "vehicle_type": vehicle_type,
            "fare_breakdown": {
                "base_fare": rates["base_fare"],
                "distance_fare": round(distance_fare),
                "time_fare": round(time_fare),
                "subtotal_before_surge": base_total,
                "surge_multiplier": surge_multiplier,
                "surge_amount": subtotal - base_total,
                "subtotal": subtotal,
                "promo_discount": discount_applied,
                "platform_fee": platform_fee,
                "platform_fee_percent": rates["platform_fee_percent"],
                "driver_earning": driver_earning,
            },
            "total_fare": total_fare,
            "currency": "MWK"
        }
    
    @classmethod
    def get_estimate(
        cls,
        pickup: Location,
        destination: Location,
        vehicle_type: str
    ) -> RideEstimateResponse:
        """
        Get fare estimate for a ride
        
        Args:
            pickup: Pickup location
            destination: Drop-off location
            vehicle_type: Type of vehicle
            
        Returns:
            RideEstimateResponse with fare details
        """
        # Calculate distance
        distance_km = cls.calculate_distance(
            pickup.latitude, pickup.longitude,
            destination.latitude, destination.longitude
        )
        
        # Estimate duration
        duration_minutes = cls.estimate_duration(distance_km, vehicle_type)
        
        # Calculate fare
        fare_calc = cls.calculate_fare(distance_km, duration_minutes, vehicle_type)
        
        return RideEstimateResponse(
            distance_km=distance_km,
            duration_minutes=duration_minutes,
            base_fare=fare_calc["fare_breakdown"]["subtotal_before_surge"],
            platform_fee=fare_calc["fare_breakdown"]["platform_fee"],
            total_fare=fare_calc["total_fare"],
            currency="MWK"
        )


# ============================================
# DRIVER MATCHING
# ============================================

class DriverMatcher:
    """
    Find and match available drivers for a ride request
    Optimized for Malawi's Kabaza market
    """
    
    # Maximum search radius in kilometers
    MAX_SEARCH_RADIUS_KM = {
        VehicleType.MOTORCYCLE.value: 5.0,   # Kabaza drivers nearby
        VehicleType.CAR.value: 8.0,           # Cars can come from further
        VehicleType.BICYCLE.value: 3.0,       # Bicycles very local
        VehicleType.MINIBUS.value: 10.0,      # Minibuses cover wider area
        VehicleType.TRUCK.value: 15.0,        # Trucks can come from far
    }
    
    # Maximum number of drivers to consider
    MAX_CANDIDATES = 20
    
    @classmethod
    def find_nearest_drivers(
        cls,
        db: Session,
        pickup_lat: float,
        pickup_lon: float,
        vehicle_type: str,
        limit: int = 10
    ) -> List[Driver]:
        """
        Find nearest available drivers
        
        Args:
            db: Database session
            pickup_lat, pickup_lon: Pickup coordinates
            vehicle_type: Required vehicle type
            limit: Maximum number of drivers to return
            
        Returns:
            List of available drivers sorted by distance
        """
        max_radius = cls.MAX_SEARCH_RADIUS_KM.get(vehicle_type, 5.0)
        
        # Get available drivers with correct vehicle type
        query = db.query(Driver).filter(
            Driver.driver_status == "online",
            Driver.is_available_for_rides == True,
            Driver.is_verified == True,
            Driver.current_latitude.isnot(None),
            Driver.current_longitude.isnot(None)
        )
        
        # Filter by vehicle type if driver has vehicles
        # (This would need a join with Vehicle table)
        
        candidates = query.limit(cls.MAX_CANDIDATES).all()
        
        # Calculate distance for each driver
        drivers_with_distance = []
        for driver in candidates:
            if driver.current_latitude and driver.current_longitude:
                distance = FareCalculator.calculate_distance(
                    pickup_lat, pickup_lon,
                    driver.current_latitude, driver.current_longitude
                )
                
                if distance <= max_radius:
                    drivers_with_distance.append({
                        "driver": driver,
                        "distance_km": distance,
                        "eta_minutes": cls._calculate_eta(distance, vehicle_type)
                    })
        
        # Sort by distance
        drivers_with_distance.sort(key=lambda x: x["distance_km"])
        
        return [d["driver"] for d in drivers_with_distance[:limit]]
    
    @classmethod
    def _calculate_eta(cls, distance_km: float, vehicle_type: str) -> int:
        """
        Calculate ETA for driver to reach pickup
        
        Args:
            distance_km: Distance from driver to pickup
            vehicle_type: Type of vehicle
            
        Returns:
            ETA in minutes
        """
        return FareCalculator.estimate_duration(distance_km, vehicle_type)
    
    @classmethod
    def select_best_driver(
        cls,
        db: Session,
        pickup_lat: float,
        pickup_lon: float,
        vehicle_type: str
    ) -> Optional[Tuple[Driver, float, int]]:
        """
        Select the best driver for a ride
        
        Selection criteria (in order of importance):
        1. Distance/EAT (closer is better)
        2. Driver rating (higher is better)
        3. Total rides completed (more experienced)
        4. Acceptance rate (higher is better)
        
        Args:
            db: Database session
            pickup_lat, pickup_lon: Pickup coordinates
            vehicle_type: Required vehicle type
            
        Returns:
            Tuple of (Driver, distance_km, eta_minutes) or None
        """
        drivers = cls.find_nearest_drivers(
            db, pickup_lat, pickup_lon, vehicle_type, limit=5
        )
        
        if not drivers:
            return None
        
        # Score each driver
        scored_drivers = []
        for driver in drivers:
            distance = FareCalculator.calculate_distance(
                pickup_lat, pickup_lon,
                driver.current_latitude, driver.current_longitude
            )
            eta = cls._calculate_eta(distance, vehicle_type)
            
            # Calculate score (lower is better for distance/eta, higher for rating)
            distance_score = 100 - (distance * 20)  # Closer = higher score
            rating_score = (driver.average_rating or 4.0) * 20
            experience_score = min(driver.total_rides_completed / 10, 10)
            
            total_score = distance_score + rating_score + experience_score
            
            scored_drivers.append({
                "driver": driver,
                "distance_km": distance,
                "eta_minutes": eta,
                "score": total_score
            })
        
        # Select highest scoring driver
        best = max(scored_drivers, key=lambda x: x["score"])
        
        return (best["driver"], best["distance_km"], best["eta_minutes"])


# ============================================
# RIDE PRICING SERVICE
# ============================================

class RidePricingService:
    """
    Complete ride pricing with mobile money support
    """
    
    @classmethod
    def get_ride_price(
        cls,
        pickup: Location,
        destination: Location,
        vehicle_type: str,
        promo_code: Optional[str] = None,
        payment_method: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get complete price breakdown for a ride
        
        Args:
            pickup: Pickup location
            destination: Drop-off location
            vehicle_type: Type of vehicle
            promo_code: Optional promo code
            payment_method: Payment method (tnm_mpamba, airtel_money, cash)
            
        Returns:
            Complete pricing details
        """
        # Calculate base fare
        estimate = FareCalculator.get_estimate(pickup, destination, vehicle_type)
        
        # Check for promo discount
        promo_discount = 0.0
        if promo_code:
            promo_discount = cls._validate_promo_code(promo_code, estimate.total_fare)
        
        # Recalculate with discount
        fare_calc = FareCalculator.calculate_fare(
            estimate.distance_km,
            estimate.duration_minutes,
            vehicle_type,
            promo_discount=promo_discount
        )
        
        # Add mobile money convenience fee (if applicable)
        mobile_money_fee = 0.0
        if payment_method in ["tnm_mpamba", "airtel_money"]:
            mobile_money_fee = 50.0  # 50 MWK convenience fee
        
        final_total = fare_calc["total_fare"] + mobile_money_fee
        
        return {
            **fare_calc,
            "mobile_money_fee": mobile_money_fee,
            "final_total": final_total,
            "promo_applied": promo_code if promo_discount > 0 else None,
            "promo_discount": promo_discount
        }
    
    @classmethod
    def _validate_promo_code(cls, code: str, fare: float) -> float:
        """
        Validate and calculate promo discount
        
        Args:
            code: Promo code
            fare: Current fare amount
            
        Returns:
            Discount amount
        """
        # Sample promo codes (would come from database in production)
        PROMOS = {
            "KABAZA50": {"type": "fixed", "value": 500.0, "max_rides": 1},
            "FIRSTRIDE": {"type": "percentage", "value": 50.0, "max_discount": 1000.0},
            "WELCOME": {"type": "percentage", "value": 30.0, "max_discount": 800.0},
        }
        
        promo = PROMOS.get(code.upper())
        if not promo:
            return 0.0
        
        if promo["type"] == "fixed":
            return min(promo["value"], fare)
        elif promo["type"] == "percentage":
            discount = fare * (promo["value"] / 100)
            max_discount = promo.get("max_discount", discount)
            return min(discount, max_discount)
        
        return 0.0


# ============================================
# ETA SERVICE
# ============================================

class ETAService:
    """
    Calculate accurate ETAs for riders and drivers
    """
    
    @classmethod
    def calculate_eta_for_rider(
        cls,
        driver_location: Tuple[float, float],
        pickup_location: Tuple[float, float],
        vehicle_type: str
    ) -> int:
        """
        Calculate ETA for driver to reach rider
        
        Args:
            driver_location: (lat, lon) of driver
            pickup_location: (lat, lon) of pickup
            vehicle_type: Type of vehicle
            
        Returns:
            ETA in minutes
        """
        distance = FareCalculator.calculate_distance(
            driver_location[0], driver_location[1],
            pickup_location[0], pickup_location[1]
        )
        
        return FareCalculator.estimate_duration(distance, vehicle_type)
    
    @classmethod
    def calculate_trip_eta(
        cls,
        pickup: Location,
        destination: Location,
        vehicle_type: str
    ) -> int:
        """
        Calculate ETA for the actual trip
        
        Args:
            pickup: Pickup location
            destination: Drop-off location
            vehicle_type: Type of vehicle
            
        Returns:
            Trip ETA in minutes
        """
        distance = FareCalculator.calculate_distance(
            pickup.latitude, pickup.longitude,
            destination.latitude, destination.longitude
        )
        
        return FareCalculator.estimate_duration(distance, vehicle_type)
    
    @classmethod
    def get_complete_eta(
        cls,
        driver_location: Optional[Tuple[float, float]],
        pickup: Location,
        destination: Location,
        vehicle_type: str
    ) -> Dict[str, Any]:
        """
        Get complete ETA breakdown
        
        Returns:
            Dictionary with pickup_eta, trip_eta, total_eta
        """
        pickup_eta = 0
        if driver_location:
            pickup_eta = cls.calculate_eta_for_rider(
                driver_location,
                (pickup.latitude, pickup.longitude),
                vehicle_type
            )
        
        trip_eta = cls.calculate_trip_eta(pickup, destination, vehicle_type)
        
        return {
            "pickup_eta_minutes": pickup_eta,
            "trip_eta_minutes": trip_eta,
            "total_eta_minutes": pickup_eta + trip_eta,
            "estimated_pickup_time": (datetime.utcnow() + timedelta(minutes=pickup_eta)).isoformat(),
            "estimated_arrival_time": (datetime.utcnow() + timedelta(minutes=pickup_eta + trip_eta)).isoformat()
        }