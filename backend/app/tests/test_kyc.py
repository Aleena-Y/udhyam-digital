"""Tests for KYC validation: GSTIN format, Udyam format, registry lookup, date checks."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.services.kyc_service import (
    validate_gstin_format, validate_udyam_format,
    lookup_gstin, lookup_udyam, validate_address_proof_date,
    load_registries
)


@pytest.fixture(autouse=True)
def load_regs():
    load_registries()


# ---------------------------------------------------------------------------
# GSTIN Format Tests
# ---------------------------------------------------------------------------
def test_valid_gstin_from_dataset():
    """GSTINs from smb_leads.csv should be valid."""
    # From L00001
    is_valid, reason = validate_gstin_format("32TTNXB7384T1ZW")
    assert is_valid, f"Should be valid: {reason}"


def test_valid_gstin_x_entity_type():
    """GSTIN with X as 4th PAN char (dataset exception) should be accepted."""
    # From L00002: 03PJNXS4821G1ZB
    is_valid, reason = validate_gstin_format("03PJNXS4821G1ZB")
    assert is_valid, f"X entity type should be accepted: {reason}"


def test_gstin_wrong_length():
    is_valid, reason = validate_gstin_format("12ABCDE1234F1Z")
    assert not is_valid
    assert "15 characters" in reason


def test_gstin_invalid_state_code():
    is_valid, reason = validate_gstin_format("99ABCDE1234F1ZA")
    assert not is_valid


def test_gstin_missing_z_at_14():
    """14th char must be Z."""
    # Modify valid GSTIN to have wrong 14th char
    is_valid, reason = validate_gstin_format("32TTNXB7384T1AW")
    assert not is_valid
    assert "14th character" in reason or "checksum" in reason


def test_gstin_lookup_found():
    result = lookup_gstin("32TTNXB7384T1ZW")
    assert result["found"]
    assert result["active"]
    assert result["record"]["legal_name"] == "Balaji Dental Care LLP"


def test_gstin_lookup_not_found():
    result = lookup_gstin("07AAXXX9999X1ZZ")
    # May fail format check or not be found
    if result["format_valid"]:
        assert not result["found"]


def test_gstin_inactive_status():
    """Test that inactive GSTINs are detected."""
    # Find an inactive GSTIN in registry
    from app.services.kyc_service import _gstin_registry
    inactive = next((v for v in _gstin_registry.values() if v["status"].lower() == "inactive"), None)
    if inactive:
        result = lookup_gstin(inactive["gstin"])
        assert result["found"]
        assert not result["active"]


# ---------------------------------------------------------------------------
# Udyam Format Tests
# ---------------------------------------------------------------------------
def test_valid_udyam_from_dataset():
    is_valid, reason = validate_udyam_format("UDYAM-KL-00-3078801")
    assert is_valid, f"Should be valid: {reason}"


def test_udyam_district_00_accepted():
    """District code '00' (dataset exception) must be accepted."""
    is_valid, reason = validate_udyam_format("UDYAM-TN-00-3866196")
    assert is_valid, f"District code 00 should be accepted: {reason}"


def test_udyam_wrong_format():
    is_valid, reason = validate_udyam_format("UDYAM-KL-3078801")
    assert not is_valid


def test_udyam_lookup_found():
    result = lookup_udyam("UDYAM-KL-00-3078801")
    assert result["found"]
    assert result["record"]["enterprise_name"] == "Balaji Dental Care LLP"


def test_udyam_lookup_not_found():
    result = lookup_udyam("UDYAM-KL-00-9999999")
    if result["format_valid"]:
        assert not result["found"]


# ---------------------------------------------------------------------------
# Address Proof Date Tests
# ---------------------------------------------------------------------------
def test_address_proof_valid_date():
    """Date within 90 days of 2026-07-15 (i.e., >= 2026-04-16)."""
    is_valid, msg = validate_address_proof_date("2026-05-01")
    assert is_valid, msg


def test_address_proof_exact_boundary():
    """Exactly 90 days before 2026-07-15 = 2026-04-16."""
    is_valid, msg = validate_address_proof_date("2026-04-16")
    assert is_valid, msg


def test_address_proof_too_old():
    """Date older than 90 days before reference should fail."""
    is_valid, msg = validate_address_proof_date("2026-01-01")
    assert not is_valid
    assert "older than" in msg


def test_address_proof_future_date():
    """Date after reference date should fail."""
    is_valid, msg = validate_address_proof_date("2026-08-01")
    assert not is_valid


def test_address_proof_invalid_format():
    """Non-date string should fail gracefully."""
    is_valid, msg = validate_address_proof_date("not-a-date")
    assert not is_valid


def test_address_proof_slash_format():
    """Accept DD/MM/YYYY format."""
    is_valid, msg = validate_address_proof_date("15/06/2026")
    assert is_valid, msg


# ---------------------------------------------------------------------------
# Registry scale tests
# ---------------------------------------------------------------------------
def test_gstin_registry_loaded():
    from app.services.kyc_service import _gstin_registry
    assert len(_gstin_registry) >= 3534, f"Expected >=3534 GSTINs, got {len(_gstin_registry)}"


def test_udyam_registry_loaded():
    from app.services.kyc_service import _udyam_registry
    assert len(_udyam_registry) >= 2723, f"Expected >=2723 Udyam records, got {len(_udyam_registry)}"
