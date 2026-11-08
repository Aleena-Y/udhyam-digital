"""
KYC router: GSTIN/Udyam validation, document upload, OCR, and status tracking.
Implements DPDP consent, data minimization, and explicit disclaimer that
OCR alone does not prove document authenticity.
"""
import os
import json
import uuid
import shutil
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import KYCRecord, Business, ConsentRecord
from app.services.kyc_service import lookup_gstin, lookup_udyam, validate_address_proof_date, ocr_extraction_disclaimer
from app.config import settings

router = APIRouter(prefix="/kyc", tags=["kyc"])

# Allowed document types
ALLOWED_DOC_TYPES = {"gst_certificate", "udyam_certificate", "signatory_id", "address_proof"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


class GSTINRequest(BaseModel):
    gstin: str
    business_id: Optional[int] = None


class UdyamRequest(BaseModel):
    udyam_number: str
    business_id: Optional[int] = None


class ConsentRequest(BaseModel):
    business_id: int
    purpose: str
    consent_text: str
    consented: bool


class KYCReviewRequest(BaseModel):
    decision: str
    reviewer_note: Optional[str] = None


@router.post("/consent")
def record_consent(req: ConsentRequest, request: Request, db: Session = Depends(get_db)):
    """Record explicit DPDP consent before any data collection."""
    biz = db.query(Business).filter(Business.id == req.business_id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    consent = ConsentRecord(
        business_id=req.business_id,
        purpose=req.purpose,
        consented=req.consented,
        consent_text=req.consent_text,
        ip_address=request.client.host if request.client else "unknown",
        consented_at=datetime.utcnow(),
    )
    db.add(consent)
    db.commit()
    return {"recorded": True, "purpose": req.purpose, "consented": req.consented}


@router.post("/validate-gstin")
def validate_gstin(req: GSTINRequest, db: Session = Depends(get_db)):
    """Validate GSTIN format and look up in mock registry."""
    result = lookup_gstin(req.gstin)

    # Update KYC record if business_id provided
    if req.business_id and result["format_valid"]:
        kyc = db.query(KYCRecord).filter(KYCRecord.business_id == req.business_id).first()
        if not kyc:
            kyc = KYCRecord(business_id=req.business_id)
            db.add(kyc)

        if result["found"] and result["active"]:
            kyc.gstin_verified = "VERIFIED"
        elif result["found"] and not result["active"]:
            kyc.gstin_verified = "FAILED"
        elif not result["found"]:
            kyc.gstin_verified = "MANUAL_REVIEW"
        else:
            kyc.gstin_verified = "FAILED"

        _update_overall_status(kyc)
        db.commit()

    return {
        "gstin": req.gstin.upper(),
        "format_valid": result["format_valid"],
        "format_reason": result["format_reason"],
        "found_in_registry": result["found"],
        "active": result["active"],
        "record": result.get("record"),
        "status": (
            "VERIFIED" if (result["found"] and result["active"])
            else "MANUAL_REVIEW" if (result["format_valid"] and not result["found"])
            else "FAILED"
        ),
    }


@router.post("/validate-udyam")
def validate_udyam(req: UdyamRequest, db: Session = Depends(get_db)):
    """Validate Udyam number format and look up in mock registry."""
    result = lookup_udyam(req.udyam_number)

    if req.business_id and result["format_valid"]:
        kyc = db.query(KYCRecord).filter(KYCRecord.business_id == req.business_id).first()
        if not kyc:
            kyc = KYCRecord(business_id=req.business_id)
            db.add(kyc)

        if result["found"]:
            kyc.udyam_verified = "VERIFIED"
        elif result["format_valid"]:
            kyc.udyam_verified = "MANUAL_REVIEW"
        else:
            kyc.udyam_verified = "FAILED"

        _update_overall_status(kyc)
        db.commit()

    return {
        "udyam_number": req.udyam_number.upper(),
        "format_valid": result["format_valid"],
        "format_reason": result["format_reason"],
        "found_in_registry": result["found"],
        "record": result.get("record"),
        "status": (
            "VERIFIED" if result["found"]
            else "MANUAL_REVIEW" if result["format_valid"]
            else "FAILED"
        ),
    }


@router.post("/upload-document")
async def upload_document(
    business_id: int = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a KYC document and perform OCR extraction.
    OCR extraction is for comparison only — does NOT constitute proof of authenticity.
    """
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid doc_type. Must be one of: {ALLOWED_DOC_TYPES}")

    biz = db.query(Business).filter(Business.id == business_id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    consent = db.query(ConsentRecord).filter(
        ConsentRecord.business_id == business_id,
        ConsentRecord.purpose == "KYC document collection",
        ConsentRecord.consented.is_(True),
        ConsentRecord.withdrawn_at.is_(None),
    ).order_by(ConsentRecord.consented_at.desc()).first()
    if not consent:
        raise HTTPException(
            status_code=400,
            detail="Explicit KYC document collection consent is required before upload",
        )

    # Validate file extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type not supported. Use: {ALLOWED_EXTENSIONS}")

    # Save file with UUID filename (don't store original filename for privacy)
    upload_dir = os.path.join(settings.UPLOAD_DIR, f"biz_{business_id}")
    os.makedirs(upload_dir, exist_ok=True)
    safe_filename = f"{doc_type}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, safe_filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Try OCR extraction
    ocr_text = ""
    ocr_fields = {}
    ocr_error = None

    try:
        import pytesseract
        from PIL import Image
        if ext in (".png", ".jpg", ".jpeg"):
            img = Image.open(file_path)
            ocr_text = pytesseract.image_to_string(img)
            ocr_fields = _extract_fields_from_ocr(ocr_text, doc_type)
    except ImportError:
        ocr_error = "Tesseract not installed. Install pytesseract and tesseract-ocr for OCR support."
    except Exception as e:
        ocr_error = f"OCR failed: {str(e)}"

    # Validate address proof date if applicable
    date_valid = None
    date_message = None
    if doc_type == "address_proof" and ocr_fields.get("date"):
        is_valid, msg = validate_address_proof_date(ocr_fields["date"])
        date_valid = is_valid
        date_message = msg

    # Update KYC record
    kyc = db.query(KYCRecord).filter(KYCRecord.business_id == business_id).first()
    if not kyc:
        kyc = KYCRecord(business_id=business_id)
        db.add(kyc)
        db.flush()

    # Update document status
    ocr_data = json.loads(kyc.ocr_data_json)
    ocr_data[doc_type] = {
        "filename": safe_filename,
        "ocr_fields": ocr_fields,
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    kyc.ocr_data_json = json.dumps(ocr_data)

    # Set document status
    if doc_type == "address_proof":
        if date_valid is False:
            setattr(kyc, f"address_proof_status", "FAILED")
        elif date_valid is True:
            setattr(kyc, f"address_proof_status", "MANUAL_REVIEW")  # OCR can't verify authenticity
        else:
            setattr(kyc, f"address_proof_status", "MANUAL_REVIEW")
    elif doc_type == "gst_certificate":
        kyc.gst_cert_status = "MANUAL_REVIEW"
    elif doc_type == "udyam_certificate":
        kyc.udyam_cert_status = "MANUAL_REVIEW"
    elif doc_type == "signatory_id":
        kyc.signatory_id_status = "MANUAL_REVIEW"

    _update_overall_status(kyc)
    db.commit()

    return {
        "uploaded": True,
        "doc_type": doc_type,
        "ocr_disclaimer": ocr_extraction_disclaimer(),
        "ocr_error": ocr_error,
        "ocr_fields": ocr_fields,
        "date_valid": date_valid,
        "date_message": date_message,
        "kyc_status": kyc.overall_status,
        "warning": "⚠️ Document upload and OCR extraction are for data collection only. Document authenticity must be verified through official registries."
    }


@router.get("/status/{business_id}")
def get_kyc_status(business_id: int, db: Session = Depends(get_db)):
    """Get current KYC status for a business."""
    kyc = db.query(KYCRecord).filter(KYCRecord.business_id == business_id).first()
    if not kyc:
        return {
            "business_id": business_id,
            "overall_status": "PENDING",
            "checks": {
                "gstin": "PENDING",
                "udyam": "PENDING",
                "gst_certificate": "PENDING",
                "udyam_certificate": "PENDING",
                "signatory_id": "PENDING",
                "address_proof": "PENDING",
            }
        }

    return {
        "business_id": business_id,
        "overall_status": kyc.overall_status,
        "checks": {
            "gstin": kyc.gstin_verified,
            "udyam": kyc.udyam_verified,
            "gst_certificate": kyc.gst_cert_status,
            "udyam_certificate": kyc.udyam_cert_status,
            "signatory_id": kyc.signatory_id_status,
            "address_proof": kyc.address_proof_status,
        },
        "failure_reasons": json.loads(kyc.failure_reasons_json),
        "updated_at": kyc.updated_at.isoformat() if kyc.updated_at else None,
    }


@router.post("/review/{business_id}")
def review_kyc(
    business_id: int,
    req: KYCReviewRequest,
    db: Session = Depends(get_db),
):
    """Apply an explicit admin review decision after registry and OCR comparison."""
    if req.decision not in {"VERIFIED", "FAILED", "MANUAL_REVIEW"}:
        raise HTTPException(
            status_code=400,
            detail="Decision must be VERIFIED, FAILED, or MANUAL_REVIEW",
        )

    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    kyc = db.query(KYCRecord).filter(KYCRecord.business_id == business_id).first()
    if not kyc:
        raise HTTPException(status_code=404, detail="No KYC record found")

    if req.decision == "VERIFIED":
        required_checks = [
            kyc.gstin_verified,
            kyc.udyam_verified,
            kyc.gst_cert_status,
            kyc.udyam_cert_status,
            kyc.signatory_id_status,
            kyc.address_proof_status,
        ]
        if any(status == "FAILED" for status in required_checks):
            raise HTTPException(
                status_code=400,
                detail="Cannot verify KYC while one or more checks have FAILED",
            )
        if any(status == "PENDING" for status in required_checks):
            raise HTTPException(
                status_code=400,
                detail="Complete all identifier and document checks before verification",
            )

    kyc.overall_status = req.decision
    reasons = json.loads(kyc.failure_reasons_json)
    if req.reviewer_note:
        reasons.append(f"Admin review: {req.reviewer_note}")
    kyc.failure_reasons_json = json.dumps(reasons[-10:])
    db.commit()

    return {
        "business_id": business_id,
        "overall_status": kyc.overall_status,
        "reviewed": True,
        "note": "Admin decision recorded. OCR remains supporting evidence and does not prove authenticity.",
    }


@router.delete("/data/{business_id}")
def delete_business_data(business_id: int, db: Session = Depends(get_db)):
    """
    DPDP data deletion: remove all KYC records and uploaded documents for a business.
    """
    # Delete KYC records
    kyc = db.query(KYCRecord).filter(KYCRecord.business_id == business_id).first()
    if kyc:
        db.delete(kyc)

    # Delete consent records
    consents = db.query(ConsentRecord).filter(ConsentRecord.business_id == business_id).all()
    for c in consents:
        db.delete(c)

    # Delete uploaded files
    upload_dir = os.path.join(settings.UPLOAD_DIR, f"biz_{business_id}")
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)

    db.commit()
    return {"deleted": True, "business_id": business_id, "message": "All KYC data and documents purged"}


def _extract_fields_from_ocr(text: str, doc_type: str) -> dict:
    """Extract structured fields from OCR text. Best-effort only."""
    import re
    fields = {}

    # Try to find dates
    date_patterns = [
        r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b',
        r'\b(\d{4}[/-]\d{2}[/-]\d{2})\b',
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        if matches:
            fields["date"] = matches[0]
            break

    # Try to find GSTIN
    gstin_match = re.search(r'\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b', text)
    if gstin_match:
        fields["gstin"] = gstin_match.group(1)

    # Try to find Udyam number
    udyam_match = re.search(r'UDYAM-[A-Z]{2}-\d{2}-\d{7}', text)
    if udyam_match:
        fields["udyam_number"] = udyam_match.group(0)

    # Raw text (truncated)
    fields["raw_text_preview"] = text[:500] if text else ""

    return fields


def _update_overall_status(kyc: KYCRecord):
    """Recalculate overall KYC status based on individual checks."""
    statuses = [
        kyc.gstin_verified,
        kyc.udyam_verified,
        kyc.gst_cert_status,
        kyc.udyam_cert_status,
        kyc.address_proof_status,
        kyc.signatory_id_status,
    ]
    if "FAILED" in statuses:
        kyc.overall_status = "FAILED"
    elif all(s == "VERIFIED" for s in statuses):
        kyc.overall_status = "VERIFIED"
    elif "MANUAL_REVIEW" in statuses:
        kyc.overall_status = "MANUAL_REVIEW"
    else:
        kyc.overall_status = "PENDING"
