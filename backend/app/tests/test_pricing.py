"""Tests for pricing service."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.services.catalogue_service import load_catalogue, get_product_by_id
from app.services.pricing_service import calculate_line_item, calculate_quote


@pytest.fixture(autouse=True)
def load_products():
    load_catalogue()


def test_tier2_uses_min_price():
    """Tier 2 cities should use price_min."""
    p = get_product_by_id("P01")
    result = calculate_line_item("P01", 1, tier=2)
    assert result["unit_price_inr"] == p.price_min
    assert result["total_monthly_inr"] == p.price_min


def test_tier1_uses_max_price():
    """Tier 1 cities should use price_max."""
    p = get_product_by_id("P01")
    result = calculate_line_item("P01", 1, tier=1)
    assert result["unit_price_inr"] == p.price_max
    assert result["total_monthly_inr"] == p.price_max


def test_quantity_multiplies_monthly():
    """Monthly cost scales with quantity."""
    p = get_product_by_id("P07")  # Business Postpaid 299 — per line
    result = calculate_line_item("P07", 5, tier=2)
    assert result["total_monthly_inr"] == p.price_min * 5
    assert result["quantity"] == 5


def test_setup_fee_not_multiplied_by_quantity():
    """Setup fee is per product, not per unit."""
    p = get_product_by_id("P09")  # Setup fee 1500
    assert p.setup_fee == 1500
    result = calculate_line_item("P09", 3, tier=2)
    assert result["setup_fee_inr"] == 1500  # Not 4500


def test_no_setup_fee_products():
    """P01 has zero setup fee."""
    p = get_product_by_id("P01")
    assert p.setup_fee == 0
    result = calculate_line_item("P01", 1, tier=2)
    assert result["setup_fee_inr"] == 0


def test_quote_totals():
    """Quote total should sum all line items."""
    items = [
        {"product_id": "P01", "quantity": 1},
        {"product_id": "P07", "quantity": 3},
    ]
    result = calculate_quote(items, city_tier=2)
    p1 = get_product_by_id("P01")
    p7 = get_product_by_id("P07")
    expected_monthly = p1.price_min * 1 + p7.price_min * 3
    assert result["total_monthly_inr"] == expected_monthly


def test_quote_max_contract():
    """Quote should use the longest contract across all products."""
    items = [
        {"product_id": "P07", "quantity": 1},  # 1 month
        {"product_id": "P06", "quantity": 1},  # 24 months
    ]
    result = calculate_quote(items, city_tier=2)
    assert result["recommended_contract_months"] == 24


def test_invalid_product_in_quote():
    """Non-existent product should produce error."""
    items = [{"product_id": "PZZZZ", "quantity": 1}]
    result = calculate_quote(items, city_tier=2)
    assert len(result["errors"]) > 0


def test_all_products_have_valid_prices():
    """All products should have price_min <= price_max."""
    from app.services.catalogue_service import get_all_products
    for p in get_all_products():
        assert p.price_min <= p.price_max, f"{p.product_id}: min {p.price_min} > max {p.price_max}"
        assert p.price_min > 0, f"{p.product_id}: price_min <= 0"


def test_install_days_positive():
    """All products should have positive install days."""
    from app.services.catalogue_service import get_all_products
    for p in get_all_products():
        assert p.typical_install_days > 0, f"{p.product_id}: install_days <= 0"
