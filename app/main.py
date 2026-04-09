from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine, Base
from app.db.migrations import run_migrations
from app.routes import auth, rides, drivers, payments, notifications
import logging
import time


# Run migrations FIRST (adds missing columns to existing tables)
run_migrations()

# THEN create any new tables that don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Kabaza API", version="1.0.0")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("kabaza.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing"""
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.3f}s"
    )
    
    return response

# CORS for React Native
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(rides.router, prefix="/api/rides", tags=["Rides"])
app.include_router(drivers.router, prefix="/api/drivers", tags=["Drivers"])
app.include_router(payments.router, prefix="/api", tags=["Payments"])          # ✅ Added
app.include_router(notifications.router, prefix="/api", tags=["Notifications"]) # ✅ Added

@app.get("/")
def root():
    return {"message": "Kabaza API is running!", "status": "active"}

@app.get("/health")
def health():
    return {"status": "healthy"}