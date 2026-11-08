"""Dashboard router: admin analytics combining dataset-derived and simulated metrics."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.analytics_service import (
    get_funnel_metrics, get_drop_reason_analysis, get_lead_source_metrics,
    get_segment_metrics, get_recovery_metrics, get_kyc_metrics, get_partner_performance
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/funnel")
def funnel_metrics(db: Session = Depends(get_db)):
    return get_funnel_metrics(db)


@router.get("/drop-reasons")
def drop_reasons(db: Session = Depends(get_db)):
    return get_drop_reason_analysis(db)


@router.get("/lead-sources")
def lead_sources(db: Session = Depends(get_db)):
    return get_lead_source_metrics(db)


@router.get("/segments")
def segment_metrics(db: Session = Depends(get_db)):
    return get_segment_metrics(db)


@router.get("/recovery")
def recovery_metrics(db: Session = Depends(get_db)):
    return get_recovery_metrics(db)


@router.get("/kyc")
def kyc_metrics(db: Session = Depends(get_db)):
    return get_kyc_metrics(db)


@router.get("/partners")
def partner_metrics(db: Session = Depends(get_db)):
    return get_partner_performance(db)


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    """Combined summary for admin dashboard overview."""
    funnel = get_funnel_metrics(db)
    segments = get_segment_metrics(db)
    recovery = get_recovery_metrics(db)
    kyc = get_kyc_metrics(db)

    return {
        "data_disclaimer": "Metrics marked 'dataset' are derived from smb_leads.csv (5,000 Q2 2026 leads). Metrics marked 'simulated' are generated for demo purposes.",
        "total_leads": funnel["total_leads"],
        "activated": funnel["activated_count"],
        "conversion_rate_pct": funnel["conversion_rate_pct"],
        "recovery_candidates": recovery["high_priority"],
        "kyc_verified": kyc["live_kyc"]["verified"],
        "top_segments": sorted(
            segments["segments"],
            key=lambda x: x["conversion_pct"],
            reverse=True
        )[:3],
        "funnel_source": funnel["source"],
    }
