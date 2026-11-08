"""Business profile router."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import Business

router = APIRouter(prefix="/business", tags=["business"])


class BusinessCreate(BaseModel):
    name: str
    business_type: Optional[str] = None
    segment: Optional[str] = "micro"
    city: Optional[str] = None
    city_tier: int = 2
    state: Optional[str] = None
    employee_count: int = 1
    num_sites: int = 1
    annual_turnover_band: Optional[str] = None
    has_gstin: bool = False
    gstin: Optional[str] = None
    has_udyam: bool = False
    udyam_number: Optional[str] = None
    current_internet: Optional[str] = None
    monthly_telecom_spend_inr: Optional[float] = None
    preferred_language: str = "English"
    user_id: Optional[int] = None


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    business_type: Optional[str] = None
    segment: Optional[str] = None
    city: Optional[str] = None
    city_tier: Optional[int] = None
    state: Optional[str] = None
    employee_count: Optional[int] = None
    num_sites: Optional[int] = None
    has_gstin: Optional[bool] = None
    gstin: Optional[str] = None
    has_udyam: Optional[bool] = None
    udyam_number: Optional[str] = None
    preferred_language: Optional[str] = None
    monthly_telecom_spend_inr: Optional[float] = None


@router.post("/")
def create_business(data: BusinessCreate, db: Session = Depends(get_db)):
    biz = Business(**data.dict())
    db.add(biz)
    db.commit()
    db.refresh(biz)
    return {"business_id": biz.id, **data.dict()}


@router.get("/{business_id}")
def get_business(business_id: int, db: Session = Depends(get_db)):
    biz = db.query(Business).filter(Business.id == business_id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    return {
        "business_id": biz.id,
        "name": biz.name,
        "business_type": biz.business_type,
        "segment": biz.segment,
        "city": biz.city,
        "city_tier": biz.city_tier,
        "state": biz.state,
        "employee_count": biz.employee_count,
        "num_sites": biz.num_sites,
        "has_gstin": biz.has_gstin,
        "has_udyam": biz.has_udyam,
        "preferred_language": biz.preferred_language,
        "monthly_telecom_spend_inr": biz.monthly_telecom_spend_inr,
        "created_at": biz.created_at.isoformat(),
    }


@router.put("/{business_id}")
def update_business(business_id: int, data: BusinessUpdate, db: Session = Depends(get_db)):
    biz = db.query(Business).filter(Business.id == business_id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    for key, val in data.dict(exclude_none=True).items():
        setattr(biz, key, val)
    db.commit()
    return {"updated": True, "business_id": business_id}
