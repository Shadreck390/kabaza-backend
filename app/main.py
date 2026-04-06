from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine, Base
from app.routes import auth

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Kabaza API", version="1.0.0")

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

@app.get("/")
def root():
    return {"message": "Kabaza API is running!", "status": "active"}

@app.get("/health")
def health():
    return {"status": "healthy"}