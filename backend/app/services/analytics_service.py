"""
Analytics service: computes dashboard metrics from actual DB data.
Clearly distinguishes dataset-derived metrics from simulated data.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.models import Lead, Order, KYCRecord, PartnerAssignment, ChannelPartner


FUNNEL_STAGES = [
    "Lead", "Contacted", "Needs assessed",
    "Quote accepted", "KYC complete", "Activated"
]


def get_funnel_metrics(db: Session) -> dict:
    """Dataset-derived funnel metrics from smb_leads.csv."""
    total = db.query(func.count(Lead.id)).scalar() or 0

    stage_counts = {}
    for stage in FUNNEL_STAGES:
        if stage == "Lead":
            stage_counts[stage] = total
        elif stage == "Activated":
            count = db.query(func.count(Lead.id)).filter(
                Lead.outcome == "Activated"
            ).scalar() or 0
            stage_counts[stage] = count
        else:
            count = db.query(func.count(Lead.id)).filter(
                Lead.stage_reached.in_(
                    FUNNEL_STAGES[FUNNEL_STAGES.index(stage):]
                )
            ).scalar() or 0
            stage_counts[stage] = count

    return {
        "source": "dataset",  # Explicitly mark as dataset-derived
        "total_leads": total,
        "funnel": [
            {
                "stage": stage,
                "count": stage_counts.get(stage, 0),
                "pct_of_prev": round(
                    stage_counts.get(stage, 0) / stage_counts.get(FUNNEL_STAGES[i-1], 1) * 100, 1
                ) if i > 0 and stage_counts.get(FUNNEL_STAGES[i-1], 0) > 0 else None
            }
            for i, stage in enumerate(FUNNEL_STAGES)
        ],
        "activated_count": stage_counts.get("Activated", 0),
        "conversion_rate_pct": round(
            stage_counts.get("Activated", 0) / total * 100, 1
        ) if total > 0 else 0,
    }


def get_drop_reason_analysis(db: Session) -> dict:
    """Dataset-derived drop reason breakdown."""
    rows = db.query(
        Lead.drop_reason,
        func.count(Lead.id).label("count"),
        func.avg(Lead.recovery_score).label("avg_recovery_score")
    ).filter(
        Lead.outcome == "Dropped",
        Lead.drop_reason != ""
    ).group_by(Lead.drop_reason).order_by(func.count(Lead.id).desc()).all()

    total_dropped = db.query(func.count(Lead.id)).filter(Lead.outcome == "Dropped").scalar() or 0

    return {
        "source": "dataset",
        "total_dropped": total_dropped,
        "reasons": [
            {
                "reason": r.drop_reason,
                "count": r.count,
                "pct": round(r.count / total_dropped * 100, 1) if total_dropped > 0 else 0,
                "avg_recovery_score": round(float(r.avg_recovery_score or 0), 1),
            }
            for r in rows
        ]
    }


def get_lead_source_metrics(db: Session) -> dict:
    """Dataset-derived lead source breakdown."""
    rows = db.query(
        Lead.lead_source,
        func.count(Lead.id).label("total"),
        func.sum(case((Lead.outcome == "Activated", 1), else_=0)).label("activated")
    ).group_by(Lead.lead_source).all()

    return {
        "source": "dataset",
        "breakdown": [
            {
                "lead_source": r.lead_source,
                "total": r.total,
                "activated": int(r.activated or 0),
                "conversion_pct": round(int(r.activated or 0) / r.total * 100, 1) if r.total > 0 else 0,
            }
            for r in rows
        ]
    }


def get_segment_metrics(db: Session) -> dict:
    """Dataset-derived segment breakdown."""
    rows = db.query(
        Lead.segment,
        func.count(Lead.id).label("total"),
        func.sum(case((Lead.outcome == "Activated", 1), else_=0)).label("activated"),
        func.avg(Lead.monthly_bundle_value_inr).label("avg_arpu"),
        func.avg(Lead.acquisition_cost_inr).label("avg_cac"),
    ).group_by(Lead.segment).all()

    return {
        "source": "dataset",
        "segments": [
            {
                "segment": r.segment,
                "total_leads": r.total,
                "activated": int(r.activated or 0),
                "conversion_pct": round(int(r.activated or 0) / r.total * 100, 1) if r.total > 0 else 0,
                "avg_arpu_inr": round(float(r.avg_arpu or 0), 0),
                "avg_cac_inr": round(float(r.avg_cac or 0), 0),
            }
            for r in rows
        ]
    }


def get_recovery_metrics(db: Session) -> dict:
    """Dataset-derived recovery candidate metrics."""
    high_score = db.query(func.count(Lead.id)).filter(
        Lead.outcome == "Dropped",
        Lead.recovery_score >= 60
    ).scalar() or 0

    medium_score = db.query(func.count(Lead.id)).filter(
        Lead.outcome == "Dropped",
        Lead.recovery_score >= 40,
        Lead.recovery_score < 60
    ).scalar() or 0

    low_score = db.query(func.count(Lead.id)).filter(
        Lead.outcome == "Dropped",
        Lead.recovery_score < 40
    ).scalar() or 0

    avg_score = db.query(func.avg(Lead.recovery_score)).filter(
        Lead.outcome == "Dropped"
    ).scalar() or 0

    # Assigned count
    assigned = db.query(func.count(PartnerAssignment.id)).scalar() or 0

    return {
        "source": "dataset+computed",
        "high_priority": high_score,  # score >= 60
        "medium_priority": medium_score,
        "low_priority": low_score,
        "avg_recovery_score": round(float(avg_score), 1),
        "assigned_to_partners": assigned,
    }


def get_kyc_metrics(db: Session) -> dict:
    """
    KYC metrics: combine dataset pipeline stats with any live KYC records.
    """
    # From dataset
    dataset_kyc_complete = db.query(func.count(Lead.id)).filter(
        Lead.kyc_complete_date.isnot(None)
    ).scalar() or 0

    dataset_missing_docs = db.query(func.count(Lead.id)).filter(
        Lead.drop_reason == "Missing GST or Udyam document"
    ).scalar() or 0

    dataset_mismatch = db.query(func.count(Lead.id)).filter(
        Lead.drop_reason == "Document details did not match"
    ).scalar() or 0

    # From live KYC records (simulated)
    live_kyc = db.query(
        KYCRecord.overall_status,
        func.count(KYCRecord.id).label("count")
    ).group_by(KYCRecord.overall_status).all()

    live_stats = {r.overall_status: r.count for r in live_kyc}

    return {
        "dataset_derived": {
            "source": "smb_leads.csv",
            "kyc_completed": dataset_kyc_complete,
            "dropped_missing_docs": dataset_missing_docs,
            "dropped_doc_mismatch": dataset_mismatch,
        },
        "live_kyc": {
            "source": "simulated",
            "total": sum(live_stats.values()),
            "verified": live_stats.get("VERIFIED", 0),
            "failed": live_stats.get("FAILED", 0),
            "manual_review": live_stats.get("MANUAL_REVIEW", 0),
            "pending": live_stats.get("PENDING", 0),
        }
    }


def get_partner_performance(db: Session) -> dict:
    """Partner assignment metrics — simulated demo data."""
    rows = db.query(
        ChannelPartner.id,
        ChannelPartner.name,
        ChannelPartner.city,
        func.count(PartnerAssignment.id).label("assigned"),
        func.sum(case((PartnerAssignment.status == "Closed", 1), else_=0)).label("closed"),
        func.sum(PartnerAssignment.commission_inr).label("total_commission"),
    ).outerjoin(PartnerAssignment, PartnerAssignment.partner_id == ChannelPartner.id
    ).group_by(ChannelPartner.id).all()

    return {
        "source": "simulated",
        "note": "Partner data is simulated for demo purposes",
        "partners": [
            {
                "partner_id": r.id,
                "name": r.name,
                "city": r.city,
                "leads_assigned": int(r.assigned or 0),
                "leads_closed": int(r.closed or 0),
                "conversion_pct": round(int(r.closed or 0) / int(r.assigned or 1) * 100, 1),
                "total_commission_inr": round(float(r.total_commission or 0), 0),
            }
            for r in rows
        ]
    }
