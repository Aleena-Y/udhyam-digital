"""
KYC Service: validates GSTIN and Udyam numbers, performs registry lookups,
handles document OCR comparison, and date validation.

Special rules (from dataset README):
- GSTIN 4th char of PAN may be 'X' (not a real entity type, but accept it)
- Udyam district code is '00' (doesn't exist in real India, but accept it)
- Address proof must be <= 90 days before DEMO_REFERENCE_DATE (2026-07-15)
  i.e. issued on or after 2026-04-16
"""
import re
import os
import csv
import json
from datetime import date, datetime
from typing import Optional, Tuple
from app.config import settings

# Registry caches
_gstin_registry: dict = {}  # gstin -> record dict
_udyam_registry: dict = {}  # udyam_number -> record dict
_registries_loaded = False


def load_registries():
    global _gstin_registry, _udyam_registry, _registries_loaded
    base = os.path.join(os.path.dirname(__file__), "..")

    # GSTIN registry
    gstin_path = os.path.normpath(os.path.join(base, settings.GSTIN_REGISTRY_PATH))
    with open(gstin_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gstin = row.get("gstin", "").strip().upper()
            if gstin:
                _gstin_registry[gstin] = {
                    "gstin": gstin,
                    "legal_name": row.get("legal_name", ""),
                    "trade_name": row.get("trade_name", ""),
                    "constitution": row.get("constitution", ""),
                    "principal_place_of_business": row.get("principal_place_of_business", ""),
                    "state": row.get("state", ""),
                    "registration_date": row.get("registration_date", ""),
                    "status": row.get("status", ""),
                }

    # Udyam registry
    udyam_path = os.path.normpath(os.path.join(base, settings.UDYAM_REGISTRY_PATH))
    with open(udyam_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            num = row.get("udyam_number", "").strip().upper()
            if num:
                _udyam_registry[num] = {
                    "udyam_number": num,
                    "enterprise_name": row.get("enterprise_name", ""),
                    "enterprise_type": row.get("enterprise_type", ""),
                    "major_activity": row.get("major_activity", ""),
                    "nic_description": row.get("nic_description", ""),
                    "state": row.get("state", ""),
                    "city": row.get("city", ""),
                    "date_of_registration": row.get("date_of_registration", ""),
                }

    _registries_loaded = True


def _ensure_loaded():
    if not _registries_loaded:
        load_registries()


# ---------------------------------------------------------------------------
# GSTIN Validation
# ---------------------------------------------------------------------------
GSTIN_CHECKSUM_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _gstin_checksum(gstin: str) -> bool:
    """Luhn-style checksum for GSTIN (positions 0-13 → check digit at 14)."""
    if len(gstin) != 15:
        return False
    factor = 1
    total = 0
    for i in range(14):
        code_point = GSTIN_CHECKSUM_CHARS.find(gstin[i].upper())
        if code_point == -1:
            return False
        addend = factor * code_point
        factor = 1 if factor == 2 else 2
        addend = (addend // 36) + (addend % 36)
        total += addend
    remainder = total % 36
    check_code_point = (36 - remainder) % 36
    return GSTIN_CHECKSUM_CHARS[check_code_point] == gstin[14].upper()


def validate_gstin_format(gstin: str) -> Tuple[bool, str]:
    """
    Validates GSTIN format:
    - 15 chars
    - First 2 digits: state code (01-37)
    - Next 10: PAN (5 alpha, 4 num, 1 alpha) — 4th char of PAN may be X
    - 13th char: entity number (1-9, A-Z)
    - 14th char: Z (always)
    - 15th char: checksum
    Returns (is_valid, reason)
    """
    gstin = gstin.strip().upper()
    if len(gstin) != 15:
        return False, "GSTIN must be exactly 15 characters"

    # State code: 01-37
    try:
        state_code = int(gstin[:2])
        if not (1 <= state_code <= 37):
            return False, f"Invalid state code: {gstin[:2]}"
    except ValueError:
        return False, f"State code must be numeric: {gstin[:2]}"

    # PAN: positions 2-11 (10 chars)
    pan = gstin[2:12]
    # PAN format: AAAAA1111A — but 4th char (index 3) can be X (dataset exception)
    pan_pattern = re.compile(r"^[A-Z]{3}[A-Z0-9][A-Z]\d{4}[A-Z]$")
    if not pan_pattern.match(pan):
        return False, f"Invalid PAN format in GSTIN: {pan}"

    # Entity number: 13th char (index 12), 1-9 or A-Z
    entity_num = gstin[12]
    if not re.match(r"[1-9A-Z]", entity_num):
        return False, f"Invalid entity number: {entity_num}"

    # 14th char must be Z
    if gstin[13] != "Z":
        return False, f"14th character must be 'Z', got '{gstin[13]}'"

    # Checksum
    if not _gstin_checksum(gstin):
        return False, "GSTIN checksum validation failed"

    return True, "Format valid"


def lookup_gstin(gstin: str) -> dict:
    """
    Returns registry record or error.
    Result: {found: bool, active: bool, record: dict|None, format_valid: bool, format_reason: str}
    """
    _ensure_loaded()
    is_valid, reason = validate_gstin_format(gstin)
    if not is_valid:
        return {
            "found": False, "active": False, "record": None,
            "format_valid": False, "format_reason": reason
        }

    gstin_upper = gstin.strip().upper()
    record = _gstin_registry.get(gstin_upper)
    if not record:
        return {
            "found": False, "active": False, "record": None,
            "format_valid": True, "format_reason": reason
        }

    active = record.get("status", "").lower() == "active"
    return {
        "found": True, "active": active, "record": record,
        "format_valid": True, "format_reason": reason
    }


# ---------------------------------------------------------------------------
# Udyam Validation
# ---------------------------------------------------------------------------
def validate_udyam_format(udyam: str) -> Tuple[bool, str]:
    """
    Format: UDYAM-XX-00-XXXXXXX
    - UDYAM prefix
    - 2-letter state code
    - district code '00' (dataset exception — accept it)
    - 7-digit registration number
    """
    udyam = udyam.strip().upper()
    pattern = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")
    if not pattern.match(udyam):
        return False, "Udyam format must be UDYAM-XX-NN-NNNNNNN"

    # District code should be '00' (dataset exception)
    parts = udyam.split("-")
    # parts: ['UDYAM', 'XX', '00', '0000000']
    district = parts[2]
    if district != "00":
        # Still accept it but note
        pass  # Accept any district code

    return True, "Format valid"


def lookup_udyam(udyam: str) -> dict:
    """Returns registry record or error."""
    _ensure_loaded()
    is_valid, reason = validate_udyam_format(udyam)
    if not is_valid:
        return {"found": False, "record": None, "format_valid": False, "format_reason": reason}

    udyam_upper = udyam.strip().upper()
    record = _udyam_registry.get(udyam_upper)
    if not record:
        return {"found": False, "record": None, "format_valid": True, "format_reason": reason}

    return {"found": True, "record": record, "format_valid": True, "format_reason": reason}


# ---------------------------------------------------------------------------
# Document date validation
# ---------------------------------------------------------------------------
def validate_address_proof_date(doc_date_str: str) -> Tuple[bool, str]:
    """
    Address proof must be issued within 90 days of DEMO_REFERENCE_DATE (2026-07-15).
    So doc_date must be >= 2026-04-16.
    """
    try:
        doc_date = datetime.strptime(doc_date_str, "%Y-%m-%d").date()
    except ValueError:
        try:
            doc_date = datetime.strptime(doc_date_str, "%d/%m/%Y").date()
        except ValueError:
            return False, f"Cannot parse date: {doc_date_str}"

    ref_date = settings.DEMO_REFERENCE_DATE
    max_age = settings.ADDRESS_PROOF_MAX_DAYS
    earliest_allowed = date(
        ref_date.year,
        ref_date.month,
        ref_date.day
    )
    from datetime import timedelta
    earliest_allowed = ref_date - timedelta(days=max_age)

    if doc_date < earliest_allowed:
        return False, (
            f"Address proof dated {doc_date} is older than {max_age} days "
            f"from reference date {ref_date}. Must be on or after {earliest_allowed}."
        )
    if doc_date > ref_date:
        return False, f"Address proof date {doc_date} is after reference date {ref_date}"

    return True, f"Address proof date {doc_date} is valid"


# ---------------------------------------------------------------------------
# OCR extraction note
# ---------------------------------------------------------------------------
def ocr_extraction_disclaimer() -> str:
    return (
        "OCR extraction provides extracted text for comparison only. "
        "It does NOT constitute proof of document authenticity. "
        "All documents must be validated against official registries."
    )
