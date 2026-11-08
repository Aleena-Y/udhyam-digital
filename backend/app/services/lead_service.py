"""
Lead recovery service: computes recovery scores from drop reasons and business profile.
Scores are explainable and rule-based (not LLM-generated).
"""
import csv
import os
from datetime import date
from typing import List, Optional
from app.config import settings

# Recovery scoring rules — configurable weights
RECOVERY_WEIGHTS = {
    # Drop reason → (base_score, is_recoverable)
    "Price too high": (60, True),
    "Quote too complex to understand": (75, True),
    "Quote took too long to arrive": (70, True),
    "Competitor offered cheaper plan": (55, True),
    "Installation delayed beyond 21 days": (65, True),
    "Customer cancelled before install": (50, True),
    "Authorised signatory not available": (80, True),
    "Owner had no time for a visit": (72, True),
    "Decided to wait": (68, True),
    "Found paperwork too long": (65, True),
    "Missing GST or Udyam document": (60, True),
    "First payment failed": (45, True),
    "Locked in with current provider": (40, True),
    "Visit not scheduled by sales": (78, True),
    # Non-recoverable
    "Site not feasible for fibre": (5, False),
    "Only wanted a mobile plan": (20, False),
    "Not interested on first call": (25, False),
    "Unreachable after 3 attempts": (15, False),
    "Wrong or invalid number": (5, False),
    "Document details did not match": (30, True),  # Could re-submit
}


def compute_recovery_score(lead_dict: dict) -> float:
    """
    Compute a recovery score (0-100) for a dropped lead.
    Returns 0 for non-dropped leads or non-recoverable reasons.
    """
    if lead_dict.get("outcome", "") != "Dropped":
        return 0.0

    drop_reason = lead_dict.get("drop_reason", "")
    base_score, is_recoverable = RECOVERY_WEIGHTS.get(drop_reason, (30, True))

    if not is_recoverable:
        return float(base_score)

    score = float(base_score)

    # Boost for high monthly spend (they can afford it)
    spend = float(lead_dict.get("monthly_telecom_spend_inr", 0) or 0)
    if spend > 5000:
        score = min(score + 10, 100)
    elif spend > 2000:
        score = min(score + 5, 100)

    # Boost for advanced funnel stage (they were interested)
    stage = lead_dict.get("stage_reached", "Lead")
    stage_weights = {
        "Lead": 0, "Contacted": 2, "Needs assessed": 5,
        "Quote accepted": 10, "KYC complete": 15
    }
    score = min(score + stage_weights.get(stage, 0), 100)

    # Boost if they had follow-up calls (shows genuine interest)
    calls = float(lead_dict.get("customer_follow_up_calls", 0) or 0)
    if calls >= 3:
        score = min(score + 8, 100)
    elif calls >= 1:
        score = min(score + 4, 100)

    # Small boost for businesses with GSTIN (easier onboarding)
    if str(lead_dict.get("has_gstin", "")).upper() in ("Y", "TRUE", "1"):
        score = min(score + 3, 100)

    return round(score, 1)


def get_recovery_explanation(lead_dict: dict) -> List[str]:
    """Return human-readable explanation of recovery score factors."""
    reasons = []
    drop_reason = lead_dict.get("drop_reason", "")
    _, is_recoverable = RECOVERY_WEIGHTS.get(drop_reason, (30, True))

    if not is_recoverable:
        reasons.append(f"Drop reason '{drop_reason}' is typically non-recoverable")
        return reasons

    reasons.append(f"Drop reason: '{drop_reason}' — addressable with follow-up")

    spend = float(lead_dict.get("monthly_telecom_spend_inr", 0) or 0)
    if spend > 5000:
        reasons.append(f"High monthly telecom spend (₹{spend:,.0f}) — good budget signal")
    elif spend > 2000:
        reasons.append(f"Moderate telecom spend (₹{spend:,.0f})")

    stage = lead_dict.get("stage_reached", "Lead")
    if stage in ("Quote accepted", "KYC complete"):
        reasons.append(f"Reached advanced stage: '{stage}' — strong intent shown")
    elif stage in ("Needs assessed",):
        reasons.append(f"Reached '{stage}' — need was identified")

    calls = float(lead_dict.get("customer_follow_up_calls", 0) or 0)
    if calls >= 1:
        reasons.append(f"Made {int(calls)} follow-up call(s) — shows genuine interest")

    return reasons


def load_leads_into_db(db_session, Lead) -> int:
    """Load smb_leads.csv into the leads table. Returns row count."""
    base = os.path.join(os.path.dirname(__file__), "..")
    path = os.path.normpath(os.path.join(base, settings.SMB_LEADS_PATH))

    def parse_date(s):
        if not s or s.strip() == "":
            return None
        try:
            return date.fromisoformat(s.strip())
        except ValueError:
            return None

    def parse_float(s):
        if not s or s.strip() == "":
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    def parse_bool(s):
        return str(s).strip().upper() in ("Y", "TRUE", "1", "YES")

    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip if already exists
            existing = db_session.query(Lead).filter_by(lead_id=row["lead_id"]).first()
            if existing:
                continue

            recovery_score = compute_recovery_score(row)
            lead = Lead(
                lead_id=row.get("lead_id", ""),
                created_date=parse_date(row.get("created_date")),
                lead_source=row.get("lead_source", ""),
                business_name=row.get("business_name", ""),
                business_type=row.get("business_type", ""),
                segment=row.get("segment", ""),
                city=row.get("city", ""),
                city_tier=int(row.get("city_tier", 2) or 2),
                state=row.get("state", ""),
                preferred_language=row.get("preferred_language", "English"),
                employee_count=int(row.get("employee_count", 1) or 1),
                num_sites=int(row.get("num_sites", 1) or 1),
                annual_turnover_band=row.get("annual_turnover_band", ""),
                has_gstin=parse_bool(row.get("has_gstin", "")),
                gstin=row.get("gstin", ""),
                has_udyam=parse_bool(row.get("has_udyam", "")),
                udyam_number=row.get("udyam_number", ""),
                current_internet=row.get("current_internet", ""),
                current_provider=row.get("current_provider", ""),
                monthly_telecom_spend_inr=parse_float(row.get("monthly_telecom_spend_inr")),
                products_of_interest=row.get("products_of_interest", ""),
                contact_name=row.get("contact_name", ""),
                contact_role=row.get("contact_role", ""),
                stage_reached=row.get("stage_reached", "Lead"),
                outcome=row.get("outcome", ""),
                drop_reason=row.get("drop_reason", ""),
                contacted_date=parse_date(row.get("contacted_date")),
                needs_assessed_date=parse_date(row.get("needs_assessed_date")),
                quote_accepted_date=parse_date(row.get("quote_accepted_date")),
                kyc_complete_date=parse_date(row.get("kyc_complete_date")),
                activated_date=parse_date(row.get("activated_date")),
                days_lead_to_activation=parse_float(row.get("days_lead_to_activation")),
                customer_follow_up_calls=parse_float(row.get("customer_follow_up_calls")),
                bundle_products=row.get("bundle_products", ""),
                monthly_bundle_value_inr=parse_float(row.get("monthly_bundle_value_inr")),
                one_time_setup_inr=parse_float(row.get("one_time_setup_inr")),
                contract_months=parse_float(row.get("contract_months")),
                churned_within_6_months=row.get("churned_within_6_months", ""),
                nps_score=parse_float(row.get("nps_score")),
                acquisition_cost_inr=parse_float(row.get("acquisition_cost_inr")),
                recovery_score=recovery_score,
            )
            db_session.add(lead)
            count += 1
            if count % 500 == 0:
                db_session.flush()

    db_session.commit()
    return count
