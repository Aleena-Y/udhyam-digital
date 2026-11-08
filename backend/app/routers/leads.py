"""Leads router: view leads, recovery candidates, and partner assignments."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from pydantic import BaseModel

from app.database import get_db
from app.models import Lead, ChannelPartner, PartnerAssignment
from app.services.lead_service import get_recovery_explanation
from app.config import settings

router = APIRouter(prefix="/leads", tags=["leads"])


class AssignRequest(BaseModel):
    partner_id: int
    notes: Optional[str] = None


@router.get("/")
def list_leads(
    outcome: Optional[str] = None,
    segment: Optional[str] = None,
    stage_reached: Optional[str] = None,
    min_recovery_score: Optional[float] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List leads with optional filtering."""
    q = db.query(Lead)
    if outcome:
        q = q.filter(Lead.outcome == outcome)
    if segment:
        q = q.filter(Lead.segment == segment)
    if stage_reached:
        q = q.filter(Lead.stage_reached == stage_reached)
    if min_recovery_score is not None:
        q = q.filter(Lead.recovery_score >= min_recovery_score)

    total = q.count()
    leads = q.order_by(Lead.created_date.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "leads": [_lead_to_dict(l) for l in leads]
    }


@router.get("/recovery-candidates")
def get_recovery_candidates(
    min_score: float = 50.0,
    unassigned_only: bool = True,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Get top recovery candidates sorted by recovery score."""
    q = db.query(Lead).filter(
        Lead.outcome == "Dropped",
        Lead.recovery_score >= min_score,
    )

    if unassigned_only:
        assigned_lead_ids = db.query(PartnerAssignment.lead_id).subquery()
        q = q.filter(Lead.id.notin_(assigned_lead_ids))

    leads = q.order_by(Lead.recovery_score.desc()).limit(limit).all()

    return {
        "count": len(leads),
        "min_score": min_score,
        "candidates": [
            {
                **_lead_to_dict(l),
                "recovery_explanation": get_recovery_explanation(_lead_to_row_dict(l))
            }
            for l in leads
        ]
    }


@router.get("/{lead_id}")
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    result = _lead_to_dict(lead)
    result["recovery_explanation"] = get_recovery_explanation(_lead_to_row_dict(lead))
    return result


@router.post("/{lead_id}/assign")
def assign_lead(lead_id: str, req: AssignRequest, db: Session = Depends(get_db)):
    """Assign a dropped lead to a channel partner."""
    lead = db.query(Lead).filter(Lead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if lead.outcome != "Dropped":
        raise HTTPException(status_code=400, detail="Only dropped leads can be assigned for recovery")

    partner = db.query(ChannelPartner).filter(
        ChannelPartner.id == req.partner_id,
        ChannelPartner.is_active == True
    ).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found or inactive")

    # Check not already assigned to this partner
    existing = db.query(PartnerAssignment).filter(
        PartnerAssignment.lead_id == lead.id,
        PartnerAssignment.partner_id == req.partner_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Lead already assigned to this partner")

    # Calculate estimated commission (demo policy: 8% of estimated monthly value)
    est_monthly = lead.monthly_telecom_spend_inr or 2000
    commission = round(est_monthly * settings.DEFAULT_COMMISSION_RATE, 0)

    assignment = PartnerAssignment(
        lead_id=lead.id,
        partner_id=req.partner_id,
        status="Assigned",
        commission_inr=commission,
        notes=req.notes,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return {
        "assignment_id": assignment.id,
        "lead_id": lead_id,
        "partner_id": req.partner_id,
        "partner_name": partner.name,
        "estimated_commission_inr": commission,
        "note": "Commission is estimated based on demo policy (8% of estimated monthly value). Actual commission subject to successful activation.",
    }


def _lead_to_dict(lead: Lead) -> dict:
    """Convert Lead ORM to dict, masking sensitive fields."""
    return {
        "id": lead.id,
        "lead_id": lead.lead_id,
        "created_date": lead.created_date.isoformat() if lead.created_date else None,
        "lead_source": lead.lead_source,
        "business_name": lead.business_name,
        "business_type": lead.business_type,
        "segment": lead.segment,
        "city": lead.city,
        "city_tier": lead.city_tier,
        "state": lead.state,
        "preferred_language": lead.preferred_language,
        "employee_count": lead.employee_count,
        "num_sites": lead.num_sites,
        "annual_turnover_band": lead.annual_turnover_band,
        "has_gstin": lead.has_gstin,
        "has_udyam": lead.has_udyam,
        "current_internet": lead.current_internet,
        "monthly_telecom_spend_inr": lead.monthly_telecom_spend_inr,
        "products_of_interest": lead.products_of_interest,
        "contact_name": lead.contact_name,
        "contact_role": lead.contact_role,
        "stage_reached": lead.stage_reached,
        "outcome": lead.outcome,
        "drop_reason": lead.drop_reason,
        "activated_date": lead.activated_date.isoformat() if lead.activated_date else None,
        "days_lead_to_activation": lead.days_lead_to_activation,
        "monthly_bundle_value_inr": lead.monthly_bundle_value_inr,
        "nps_score": lead.nps_score,
        "recovery_score": lead.recovery_score,
        # MASKED for privacy: gstin, udyam_number, contact details beyond name
    }


def _lead_to_row_dict(lead: Lead) -> dict:
    """Convert Lead to dict for scoring functions (includes all fields)."""
    return {
        "outcome": lead.outcome,
        "drop_reason": lead.drop_reason,
        "monthly_telecom_spend_inr": lead.monthly_telecom_spend_inr,
        "stage_reached": lead.stage_reached,
        "customer_follow_up_calls": lead.customer_follow_up_calls,
        "has_gstin": "Y" if lead.has_gstin else "N",
    }
