"""Tests for catalogue eligibility rules."""
import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.services.catalogue_service import load_catalogue, check_eligibility, filter_eligible_products, get_product_by_id


@pytest.fixture(autouse=True)
def load_products():
    load_catalogue()


def test_all_products_loaded():
    from app.services.catalogue_service import get_all_products
    products = get_all_products()
    assert len(products) == 25, f"Expected 25 products, got {len(products)}"


def test_tier1_only_product_blocked_for_tier2():
    """P03 Biz Fibre 1G is only available in Tier 1."""
    p = get_product_by_id("P03")
    assert p is not None
    assert p.available_tiers == [1], f"P03 tiers: {p.available_tiers}"

    result = check_eligibility(p, city_tier=2, employee_count=5, num_sites=1, has_gstin=True, gstin_active=True, bundle_product_ids=[])
    assert not result["eligible"]
    assert any("Tier" in r for r in result["reasons"])


def test_tier1_product_allowed_for_tier1():
    p = get_product_by_id("P03")
    result = check_eligibility(p, city_tier=1, employee_count=10, num_sites=1, has_gstin=True, gstin_active=True, bundle_product_ids=[])
    assert result["eligible"], f"Should be eligible: {result['reasons']}"


def test_min_employees_enforcement():
    """P05 ILL-20 requires min 10 employees."""
    p = get_product_by_id("P05")
    assert p.min_employees == 10

    result = check_eligibility(p, city_tier=1, employee_count=5, num_sites=1, has_gstin=True, gstin_active=True, bundle_product_ids=[])
    assert not result["eligible"]
    assert any("employee" in r.lower() for r in result["reasons"])


def test_min_employees_satisfied():
    p = get_product_by_id("P05")
    result = check_eligibility(p, city_tier=1, employee_count=10, num_sites=1, has_gstin=True, gstin_active=True, bundle_product_ids=[])
    assert result["eligible"], f"Should be eligible: {result['reasons']}"


def test_min_sites_enforcement():
    """P10 SD-WAN requires min 3 sites."""
    p = get_product_by_id("P10")
    assert p.min_sites == 3

    result = check_eligibility(p, city_tier=1, employee_count=10, num_sites=2, has_gstin=True, gstin_active=True, bundle_product_ids=["P01"])
    assert not result["eligible"]
    assert any("site" in r.lower() for r in result["reasons"])


def test_gstin_required_enforcement():
    """P05 requires GSTIN."""
    p = get_product_by_id("P05")
    assert p.requires_gstin

    result = check_eligibility(p, city_tier=1, employee_count=10, num_sites=1, has_gstin=False, gstin_active=False, bundle_product_ids=[])
    assert not result["eligible"]
    assert any("GSTIN" in r for r in result["reasons"])


def test_gstin_not_required_for_basic_products():
    """P01 Biz Fibre 100 does not require GSTIN."""
    p = get_product_by_id("P01")
    assert not p.requires_gstin

    result = check_eligibility(p, city_tier=2, employee_count=1, num_sites=1, has_gstin=False, gstin_active=False, bundle_product_ids=[])
    assert result["eligible"], f"Should be eligible: {result['reasons']}"


def test_product_dependency_enforcement():
    """P09 Backup 4G Failover requires P01|P02|P03|P05|P06."""
    p = get_product_by_id("P09")
    assert len(p.requires_one_of) > 0

    # Without dependency
    result = check_eligibility(p, city_tier=2, employee_count=1, num_sites=1, has_gstin=False, gstin_active=False, bundle_product_ids=[])
    assert not result["eligible"]
    assert any("Requires one of" in r for r in result["reasons"])

    # With dependency satisfied
    result = check_eligibility(p, city_tier=2, employee_count=1, num_sites=1, has_gstin=False, gstin_active=False, bundle_product_ids=["P01"])
    assert result["eligible"], f"Should be eligible with P01: {result['reasons']}"


def test_sd_wan_dependencies():
    """P10 SD-WAN requires connectivity product."""
    p = get_product_by_id("P10")
    assert "P01" in p.requires_one_of or "P05" in p.requires_one_of

    result = check_eligibility(p, city_tier=1, employee_count=10, num_sites=3, has_gstin=True, gstin_active=True, bundle_product_ids=["P05"])
    assert result["eligible"], f"Should be eligible with P05: {result['reasons']}"


def test_multiple_rule_violations():
    """P10 SD-WAN: test multiple violations at once."""
    p = get_product_by_id("P10")
    result = check_eligibility(p, city_tier=2, employee_count=5, num_sites=1, has_gstin=False, gstin_active=False, bundle_product_ids=[])
    assert not result["eligible"]
    assert len(result["reasons"]) >= 3  # min_employees, min_sites, requires_gstin, requires_one_of


def test_filter_returns_all_products():
    products = filter_eligible_products(city_tier=2, employee_count=1, num_sites=1, has_gstin=False, gstin_active=False)
    assert len(products) == 25


def test_p04_airfiber_available_tier1_and_tier2():
    """P04 5G AirFiber should be available in both tiers."""
    p = get_product_by_id("P04")
    assert 1 in p.available_tiers
    assert 2 in p.available_tiers
