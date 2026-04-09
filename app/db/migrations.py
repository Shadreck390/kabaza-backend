"""
Database Migrations for Kabaza
Handles table creation and schema updates
Supports TNM Mpamba & Airtel Money integration
"""

from sqlalchemy import text
from app.db.database import engine
import logging

logger = logging.getLogger(__name__)


def table_exists(conn, table_name):
    """Check if a table exists in the database"""
    result = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
    ), {"table_name": table_name})
    return result.fetchone() is not None


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    result = conn.execute(text(f"PRAGMA table_info({table_name})"))
    columns = [row[1] for row in result.fetchall()]
    return column_name in columns


def run_migrations():
    """Run database migrations - creates all tables and adds missing columns"""
    print("🔍 Running database migrations...")
    
    with engine.connect() as conn:
        
        # ============================================
        # CREATE ALL TABLES
        # ============================================
        
        # Users table (Extended)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                name TEXT,
                email TEXT,
                password TEXT,
                role TEXT DEFAULT 'rider',
                is_verified BOOLEAN DEFAULT 0,
                profile_image TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                last_login DATETIME
            )
        """))
        
        # Riders table (NEW - for rider profiles)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS riders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                full_name TEXT,
                phone TEXT,
                email TEXT,
                profile_photo TEXT,
                status TEXT DEFAULT 'active',
                is_verified BOOLEAN DEFAULT 0,
                average_rating FLOAT DEFAULT 5.0,
                total_ratings INTEGER DEFAULT 0,
                total_rides_taken INTEGER DEFAULT 0,
                total_rides_cancelled INTEGER DEFAULT 0,
                wallet_balance FLOAT DEFAULT 0.0,
                total_spent FLOAT DEFAULT 0.0,
                default_payment_method TEXT DEFAULT 'cash',
                preferred_vehicle_type TEXT DEFAULT 'motorcycle',
                referral_code TEXT UNIQUE,
                referred_by TEXT,
                referral_credits FLOAT DEFAULT 0.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                last_ride_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """))
        
        # Drivers table (Extended with mobile money support)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS drivers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id TEXT UNIQUE,
                user_id INTEGER UNIQUE,
                full_name TEXT,
                national_id TEXT UNIQUE,
                date_of_birth DATETIME,
                phone TEXT UNIQUE,
                alternative_phone TEXT,
                address TEXT,
                city TEXT DEFAULT 'Lilongwe',
                license_number TEXT UNIQUE,
                license_expiry DATETIME,
                license_front_image TEXT,
                license_back_image TEXT,
                profile_photo TEXT,
                verification_status TEXT DEFAULT 'pending',
                is_verified BOOLEAN DEFAULT 0,
                verified_at DATETIME,
                driver_status TEXT DEFAULT 'offline',
                last_status_update DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                is_available_for_rides BOOLEAN DEFAULT 0,
                current_location JSON,
                last_location JSON,
                last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                average_rating FLOAT DEFAULT 0.0,
                total_ratings INTEGER DEFAULT 0,
                total_rides_completed INTEGER DEFAULT 0,
                total_rides_cancelled INTEGER DEFAULT 0,
                
                -- Mobile Money Payout Details
                payout_method TEXT DEFAULT 'tnm_mpamba',
                tnm_mpamba_phone TEXT,
                tnm_mpamba_registered_name TEXT,
                airtel_money_phone TEXT,
                airtel_money_registered_name TEXT,
                bank_name TEXT,
                bank_account_number TEXT,
                bank_account_name TEXT,
                bank_branch TEXT,
                
                -- Earnings
                total_earnings FLOAT DEFAULT 0.0,
                available_balance FLOAT DEFAULT 0.0,
                pending_balance FLOAT DEFAULT 0.0,
                total_paid_out FLOAT DEFAULT 0.0,
                commission_rate FLOAT DEFAULT 15.0,
                
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                last_online_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        
        # Vehicles table (NEW)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER NOT NULL,
                vehicle_type TEXT NOT NULL,
                make TEXT NOT NULL,
                model TEXT NOT NULL,
                year INTEGER NOT NULL,
                color TEXT NOT NULL,
                registration_number TEXT UNIQUE NOT NULL,
                registration_expiry DATETIME,
                insurance_provider TEXT,
                insurance_policy_number TEXT,
                insurance_expiry DATETIME,
                cof_number TEXT,
                cof_expiry DATETIME,
                front_image TEXT,
                back_image TEXT,
                left_side_image TEXT,
                right_side_image TEXT,
                registration_image TEXT,
                insurance_image TEXT,
                is_verified BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                has_helmet BOOLEAN DEFAULT 0,
                has_reflective_jacket BOOLEAN DEFAULT 0,
                max_passengers INTEGER DEFAULT 1,
                has_ac BOOLEAN DEFAULT 0,
                max_luggage INTEGER DEFAULT 2,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                FOREIGN KEY (driver_id) REFERENCES drivers(id) ON DELETE CASCADE
            )
        """))
        
        # Rides table (Extended with mobile money payment tracking)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ride_id TEXT UNIQUE NOT NULL,
                rider_id INTEGER NOT NULL,
                driver_id INTEGER,
                rider_name TEXT,
                driver_name TEXT,
                pickup_location JSON NOT NULL,
                destination JSON NOT NULL,
                waypoints JSON,
                distance_km FLOAT DEFAULT 0.0,
                duration_minutes FLOAT DEFAULT 0.0,
                fare FLOAT DEFAULT 0.0,
                platform_fee FLOAT DEFAULT 0.0,
                driver_earning FLOAT DEFAULT 0.0,
                tip_amount FLOAT DEFAULT 0.0,
                status TEXT DEFAULT 'requested',
                requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                accepted_at DATETIME,
                started_at DATETIME,
                completed_at DATETIME,
                cancelled_at DATETIME,
                driver_current_location JSON,
                last_location_update DATETIME,
                
                -- Payment Information (Mobile Money Support)
                payment_method TEXT DEFAULT 'cash',
                payment_status TEXT DEFAULT 'pending',
                payment_provider TEXT,
                payment_phone TEXT,
                payment_transaction_id TEXT,
                payment_reference TEXT,
                payment_completed_at DATETIME,
                tnm_mpamba_transaction_id TEXT,
                tnm_mpamba_status TEXT,
                airtel_money_transaction_id TEXT,
                airtel_money_status TEXT,
                
                is_scheduled BOOLEAN DEFAULT 0,
                scheduled_for DATETIME,
                cancellation_reason TEXT,
                estimated_fare FLOAT DEFAULT 0.0,
                surge_multiplier FLOAT DEFAULT 1.0,
                discount_applied FLOAT DEFAULT 0.0,
                final_fare FLOAT DEFAULT 0.0,
                rider_rating INTEGER,
                driver_rating INTEGER,
                rider_feedback TEXT,
                driver_feedback TEXT,
                route_polyline TEXT,
                tracking_updates JSON,
                
                FOREIGN KEY (rider_id) REFERENCES riders(id),
                FOREIGN KEY (driver_id) REFERENCES drivers(id)
            )
        """))
        
        # Driver Earnings table (NEW)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS driver_earnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER NOT NULL,
                ride_id INTEGER NOT NULL,
                ride_fare FLOAT NOT NULL,
                platform_fee FLOAT NOT NULL,
                driver_earning FLOAT NOT NULL,
                tip_amount FLOAT DEFAULT 0.0,
                status TEXT DEFAULT 'pending',
                cleared_at DATETIME,
                paid_out_at DATETIME,
                payout_id INTEGER,
                rider_payment_method TEXT,
                rider_payment_reference TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (driver_id) REFERENCES drivers(id),
                FOREIGN KEY (ride_id) REFERENCES rides(id)
            )
        """))
        
        # Payouts table (NEW - for driver withdrawals via mobile money)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER NOT NULL,
                amount FLOAT NOT NULL,
                fee FLOAT DEFAULT 0.0,
                net_amount FLOAT NOT NULL,
                payout_method TEXT NOT NULL,
                
                -- TNM Mpamba
                tnm_mpamba_phone TEXT,
                tnm_mpamba_transaction_id TEXT,
                tnm_mpamba_status TEXT,
                
                -- Airtel Money
                airtel_money_phone TEXT,
                airtel_money_transaction_id TEXT,
                airtel_money_status TEXT,
                
                -- Bank
                bank_name TEXT,
                bank_account_number TEXT,
                bank_account_name TEXT,
                bank_reference TEXT,
                
                status TEXT DEFAULT 'pending',
                reference_number TEXT UNIQUE NOT NULL,
                completed_at DATETIME,
                failure_reason TEXT,
                requested_by INTEGER,
                approved_by INTEGER,
                approved_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                FOREIGN KEY (driver_id) REFERENCES drivers(id)
            )
        """))
        
        # Rider Payment Methods table (NEW)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rider_payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rider_id INTEGER NOT NULL,
                method_type TEXT NOT NULL,
                is_default BOOLEAN DEFAULT 0,
                
                -- TNM Mpamba
                tnm_mpamba_phone TEXT,
                tnm_mpamba_nickname TEXT,
                
                -- Airtel Money
                airtel_money_phone TEXT,
                airtel_money_nickname TEXT,
                
                -- Card
                card_last4 TEXT,
                card_brand TEXT,
                card_expiry_month INTEGER,
                card_expiry_year INTEGER,
                card_token TEXT,
                
                is_verified BOOLEAN DEFAULT 0,
                verified_at DATETIME,
                last_used_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rider_id) REFERENCES riders(id) ON DELETE CASCADE
            )
        """))
        
        # Favorite Locations table (NEW)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS favorite_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rider_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                address TEXT NOT NULL,
                latitude FLOAT NOT NULL,
                longitude FLOAT NOT NULL,
                place_id TEXT,
                icon TEXT,
                is_frequent BOOLEAN DEFAULT 0,
                visit_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_used_at DATETIME,
                FOREIGN KEY (rider_id) REFERENCES riders(id) ON DELETE CASCADE
            )
        """))
        
        # Wallet Transactions table (NEW)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS wallet_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rider_id INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                amount FLOAT NOT NULL,
                balance_before FLOAT NOT NULL,
                balance_after FLOAT NOT NULL,
                payment_method TEXT,
                payment_reference TEXT,
                tnm_mpamba_transaction_id TEXT,
                airtel_money_transaction_id TEXT,
                reference_type TEXT,
                reference_id INTEGER,
                description TEXT,
                status TEXT DEFAULT 'pending',
                completed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rider_id) REFERENCES riders(id)
            )
        """))
        
        # Payments table (Legacy - kept for compatibility)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                ride_id TEXT,
                amount FLOAT NOT NULL,
                payment_method TEXT DEFAULT 'cash',
                payment_status TEXT DEFAULT 'pending',
                transaction_id TEXT,
                mpesa_receipt TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME
            )
        """))
        
        # Notifications table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                type TEXT DEFAULT 'info',
                is_read BOOLEAN DEFAULT 0,
                data JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Chat messages table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE NOT NULL,
                ride_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                sender_role TEXT NOT NULL,
                message TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                is_read BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # OTP table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                code TEXT NOT NULL,
                is_used BOOLEAN DEFAULT 0,
                expires_at DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # ============================================
        # ADD MISSING COLUMNS TO EXISTING TABLES
        # ============================================
        
        # Users table columns
        if table_exists(conn, "users"):
            result = conn.execute(text("PRAGMA table_info(users)"))
            existing_columns = [row[1] for row in result.fetchall()]
            
            user_columns_to_add = {
                'updated_at': 'DATETIME',
                'last_login': 'DATETIME',
                'profile_image': 'TEXT',
            }
            
            for col, col_type in user_columns_to_add.items():
                if col not in existing_columns:
                    print(f"📦 Adding {col} to users table...")
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {col_type}"))
                        conn.commit()
                    except Exception as e:
                        print(f"   ⚠️ Could not add {col}: {e}")
        
        # Drivers table columns
        if table_exists(conn, "drivers"):
            result = conn.execute(text("PRAGMA table_info(drivers)"))
            existing_columns = [row[1] for row in result.fetchall()]
            
            driver_columns_to_add = {
                'user_id': 'INTEGER',
                'full_name': 'TEXT',
                'national_id': 'TEXT',
                'payout_method': 'TEXT DEFAULT "tnm_mpamba"',
                'tnm_mpamba_phone': 'TEXT',
                'airtel_money_phone': 'TEXT',
                'available_balance': 'FLOAT DEFAULT 0.0',
                'pending_balance': 'FLOAT DEFAULT 0.0',
                'total_paid_out': 'FLOAT DEFAULT 0.0',
                'commission_rate': 'FLOAT DEFAULT 15.0',
            }
            
            for col, col_type in driver_columns_to_add.items():
                if col not in existing_columns:
                    print(f"📦 Adding {col} to drivers table...")
                    try:
                        conn.execute(text(f"ALTER TABLE drivers ADD COLUMN {col} {col_type}"))
                        conn.commit()
                    except Exception as e:
                        print(f"   ⚠️ Could not add {col}: {e}")
        
        # Rides table columns
        if table_exists(conn, "rides"):
            result = conn.execute(text("PRAGMA table_info(rides)"))
            existing_columns = [row[1] for row in result.fetchall()]
            
            ride_columns_to_add = {
                'platform_fee': 'FLOAT DEFAULT 0.0',
                'driver_earning': 'FLOAT DEFAULT 0.0',
                'tip_amount': 'FLOAT DEFAULT 0.0',
                'payment_provider': 'TEXT',
                'payment_phone': 'TEXT',
                'payment_transaction_id': 'TEXT',
                'payment_completed_at': 'DATETIME',
                'tnm_mpamba_transaction_id': 'TEXT',
                'airtel_money_transaction_id': 'TEXT',
                'estimated_fare': 'FLOAT DEFAULT 0.0',
                'surge_multiplier': 'FLOAT DEFAULT 1.0',
                'discount_applied': 'FLOAT DEFAULT 0.0',
                'final_fare': 'FLOAT DEFAULT 0.0',
                'rider_rating': 'INTEGER',
                'driver_rating': 'INTEGER',
                'rider_feedback': 'TEXT',
                'driver_feedback': 'TEXT',
                'route_polyline': 'TEXT',
                'tracking_updates': 'JSON',
            }
            
            for col, col_type in ride_columns_to_add.items():
                if col not in existing_columns:
                    print(f"📦 Adding {col} to rides table...")
                    try:
                        conn.execute(text(f"ALTER TABLE rides ADD COLUMN {col} {col_type}"))
                        conn.commit()
                    except Exception as e:
                        print(f"   ⚠️ Could not add {col}: {e}")
        
        # ============================================
        # CREATE INDEXES
        # ============================================
        print("🔍 Creating indexes...")
        
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)",
            "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
            "CREATE INDEX IF NOT EXISTS idx_riders_user_id ON riders(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_drivers_user_id ON drivers(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_drivers_driver_status ON drivers(driver_status)",
            "CREATE INDEX IF NOT EXISTS idx_drivers_verification_status ON drivers(verification_status)",
            "CREATE INDEX IF NOT EXISTS idx_vehicles_driver_id ON vehicles(driver_id)",
            "CREATE INDEX IF NOT EXISTS idx_rides_rider_id ON rides(rider_id)",
            "CREATE INDEX IF NOT EXISTS idx_rides_driver_id ON rides(driver_id)",
            "CREATE INDEX IF NOT EXISTS idx_rides_status ON rides(status)",
            "CREATE INDEX IF NOT EXISTS idx_rides_payment_status ON rides(payment_status)",
            "CREATE INDEX IF NOT EXISTS idx_driver_earnings_driver_id ON driver_earnings(driver_id)",
            "CREATE INDEX IF NOT EXISTS idx_driver_earnings_ride_id ON driver_earnings(ride_id)",
            "CREATE INDEX IF NOT EXISTS idx_payouts_driver_id ON payouts(driver_id)",
            "CREATE INDEX IF NOT EXISTS idx_payouts_status ON payouts(status)",
            "CREATE INDEX IF NOT EXISTS idx_rider_payment_methods_rider_id ON rider_payment_methods(rider_id)",
            "CREATE INDEX IF NOT EXISTS idx_favorite_locations_rider_id ON favorite_locations(rider_id)",
            "CREATE INDEX IF NOT EXISTS idx_wallet_transactions_rider_id ON wallet_transactions(rider_id)",
            "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_ride_id ON chat_messages(ride_id)",
            "CREATE INDEX IF NOT EXISTS idx_otps_phone ON otps(phone)",
        ]
        
        for index_sql in indexes:
            try:
                conn.execute(text(index_sql))
            except Exception as e:
                print(f"   ⚠️ Could not create index: {e}")
        
        conn.commit()
    
    print("✅ Database migrations completed successfully!")


def reset_database():
    """WARNING: Drops all tables and recreates them"""
    print("⚠️ WARNING: This will delete all data!")
    confirm = input("Type 'YES' to confirm: ")
    
    if confirm != "YES":
        print("❌ Reset cancelled.")
        return
    
    with engine.connect() as conn:
        # Drop all tables
        tables = [
            "wallet_transactions", "favorite_locations", "rider_payment_methods",
            "payouts", "driver_earnings", "vehicles", "payments",
            "rides", "riders", "drivers", "notifications", "chat_messages",
            "otps", "users"
        ]
        
        for table in tables:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                print(f"✅ Dropped {table}")
            except Exception as e:
                print(f"⚠️ Could not drop {table}: {e}")
        
        conn.commit()
    
    # Recreate all tables
    run_migrations()
    print("✅ Database reset completed!")


if __name__ == "__main__":
    run_migrations()