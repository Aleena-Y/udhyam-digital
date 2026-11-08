"""
Udyam Digital API — Accel Business MSME Acquisition Platform
Main FastAPI application entry point.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import engine, SessionLocal
from app.models import Base, User, ChannelPartner
from app.config import settings
from app.services.catalogue_service import load_catalogue
from app.services.kyc_service import load_registries
from app.routers import auth, chatbot, recommendations, quotes, kyc, orders, leads, dashboard, business
from app.routers.auth import get_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Udyam Digital API...")

    # Create DB tables
    Base.metadata.create_all(bind=engine)

    # Create uploads directory
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Load product catalogue into memory
    try:
        products = load_catalogue()
        logger.info(f"Loaded {len(products)} products from catalogue")
    except Exception as e:
        logger.error(f"Failed to load catalogue: {e}")

    # Load KYC registries into memory
    try:
        load_registries()
        logger.info("Loaded GSTIN and Udyam registries")
    except Exception as e:
        logger.error(f"Failed to load registries: {e}")

    # Load smb_leads.csv into DB
    try:
        from app.services.lead_service import load_leads_into_db
        from app.models import Lead
        db = SessionLocal()
        count = load_leads_into_db(db, Lead)
        db.close()
        if count > 0:
            logger.info(f"Loaded {count} leads from smb_leads.csv")
        else:
            logger.info("Leads already loaded")
    except Exception as e:
        logger.error(f"Failed to load leads: {e}")

    # Seed demo users and channel partners
    try:
        _seed_demo_data()
    except Exception as e:
        logger.error(f"Failed to seed demo data: {e}")

    logger.info("Udyam Digital API ready!")
    yield
    logger.info("Shutting down...")


def _seed_demo_data():
    """Seed demo admin, partner and channel partner records."""
    db = SessionLocal()
    try:
        # Demo admin
        if not db.query(User).filter(User.email == "admin@accel.demo").first():
            db.add(User(
                email="admin@accel.demo",
                hashed_password=get_password_hash("admin123"),
                full_name="Admin User",
                role="admin",
            ))

        # Demo partner user
        if not db.query(User).filter(User.email == "partner@accel.demo").first():
            db.add(User(
                email="partner@accel.demo",
                hashed_password=get_password_hash("partner123"),
                full_name="Channel Partner",
                role="partner",
            ))

        # Demo customer
        if not db.query(User).filter(User.email == "customer@accel.demo").first():
            db.add(User(
                email="customer@accel.demo",
                hashed_password=get_password_hash("customer123"),
                full_name="Demo Customer",
                role="customer",
            ))

        db.commit()

        # Seed channel partners
        if db.query(ChannelPartner).count() == 0:
            partners_data = [
                {"name": "TechServe Solutions", "region": "South", "city": "Bangalore", "tier": 1},
                {"name": "BizConnect Partners", "region": "West", "city": "Mumbai", "tier": 1},
                {"name": "NorthStar Telecom", "region": "North", "city": "Delhi", "tier": 1},
                {"name": "Eastern Connect", "region": "East", "city": "Kolkata", "tier": 1},
                {"name": "Coimbatore NetPro", "region": "South", "city": "Coimbatore", "tier": 2},
                {"name": "Ludhiana BizTech", "region": "North", "city": "Ludhiana", "tier": 2},
            ]
            for p in partners_data:
                db.add(ChannelPartner(**p, is_active=True))
            db.commit()
            logger.info(f"Seeded {len(partners_data)} channel partners")

    finally:
        db.close()


# Create FastAPI app
app = FastAPI(
    title="Udyam Digital API",
    description="Accel Business MSME Acquisition & Onboarding Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware (allow frontend dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(chatbot.router)
app.include_router(recommendations.router)
app.include_router(quotes.router)
app.include_router(kyc.router)
app.include_router(orders.router)
app.include_router(leads.router)
app.include_router(dashboard.router)
app.include_router(business.router)


@app.get("/")
def root():
    return {
        "app": "Udyam Digital API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "online",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
