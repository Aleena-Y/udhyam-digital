"""
Pricing service: deterministic price calculation from catalogue data.
LLM never calculates or overrides prices.
"""
from typing import List, Optional
from app.services.catalogue_service import get_product_by_id


def calculate_line_item(product_id: str, quantity: int, tier: int = 2) -> dict:
    """
    Calculate price for a single product + quantity.
    Uses min price (tier 1 gets max). Returns deterministic values.
    """
    product = get_product_by_id(product_id)
    if not product:
        return {"error": f"Product {product_id} not found"}

    # Pricing logic: Tier-1 cities pay max, Tier-2 pay min
    if tier == 1:
        unit_price = product.price_max
    else:
        unit_price = product.price_min

    total_monthly = unit_price * quantity
    total_setup = product.setup_fee  # Setup fee is per product, not per qty

    return {
        "product_id": product_id,
        "product_name": product.product_name,
        "category": product.category,
        "unit": product.unit,
        "quantity": quantity,
        "unit_price_inr": unit_price,
        "total_monthly_inr": total_monthly,
        "setup_fee_inr": total_setup,
        "min_contract_months": product.min_contract_months,
        "typical_install_days": product.typical_install_days,
    }


def calculate_quote(
    line_items: List[dict],
    city_tier: int = 2,
) -> dict:
    """
    Calculate total quote from list of {product_id, quantity} dicts.
    Returns enriched line items + totals.
    """
    enriched = []
    total_monthly = 0
    total_setup = 0
    max_contract = 0
    max_install_days = 0
    errors = []

    for item in line_items:
        pid = item.get("product_id", "")
        qty = int(item.get("quantity", 1))
        result = calculate_line_item(pid, qty, city_tier)
        if "error" in result:
            errors.append(result["error"])
        else:
            enriched.append(result)
            total_monthly += result["total_monthly_inr"]
            total_setup += result["setup_fee_inr"]
            max_contract = max(max_contract, result["min_contract_months"])
            max_install_days = max(max_install_days, result["typical_install_days"])

    return {
        "line_items": enriched,
        "total_monthly_inr": round(total_monthly, 2),
        "total_setup_inr": round(total_setup, 2),
        "recommended_contract_months": max_contract,
        "estimated_install_days": max_install_days,
        "errors": errors,
    }


def get_max_install_days_for_products(product_ids: List[str]) -> int:
    """Return the maximum typical_install_days across all products in a bundle."""
    max_days = 0
    for pid in product_ids:
        p = get_product_by_id(pid)
        if p:
            max_days = max(max_days, p.typical_install_days)
    return max_days or 7
