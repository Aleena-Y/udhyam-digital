"""
Catalogue service: loads product_catalogue.csv and enforces all eligibility rules.
Business rules are DETERMINISTIC — LLM never makes eligibility decisions.
"""
import csv
import os
from typing import List, Optional
from app.config import settings


class Product:
    def __init__(self, row: dict):
        self.product_id = row["product_id"].strip()
        self.category = row["category"].strip()
        self.product_name = row["product_name"].strip()
        self.description = row["description"].strip()
        self.unit = row["unit"].strip()
        self.price_min = float(row["price_min_inr_per_month"])
        self.price_max = float(row["price_max_inr_per_month"])
        self.setup_fee = float(row["one_time_setup_inr"])
        self.min_contract_months = int(row["min_contract_months"])
        self.available_tiers = [int(t) for t in row["available_city_tiers"].split(";")]
        self.min_employees = int(row["min_employees"])
        self.min_sites = int(row["min_sites"])
        self.requires_gstin = row["requires_gstin"].strip().upper() == "Y"
        raw_dep = row.get("requires_one_of", "").strip()
        self.requires_one_of = [p.strip() for p in raw_dep.split("|") if p.strip()] if raw_dep else []
        self.typical_install_days = int(row["typical_install_days"])
        self.target_segments = [s.strip() for s in row["target_segments"].split(";")]

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "category": self.category,
            "product_name": self.product_name,
            "description": self.description,
            "unit": self.unit,
            "price_min": self.price_min,
            "price_max": self.price_max,
            "setup_fee": self.setup_fee,
            "min_contract_months": self.min_contract_months,
            "available_tiers": self.available_tiers,
            "min_employees": self.min_employees,
            "min_sites": self.min_sites,
            "requires_gstin": self.requires_gstin,
            "requires_one_of": self.requires_one_of,
            "typical_install_days": self.typical_install_days,
            "target_segments": self.target_segments,
        }


# In-memory product store (loaded once at startup)
_products: List[Product] = []
_products_by_id: dict = {}


def load_catalogue():
    """Load product catalogue from CSV. Called at app startup."""
    global _products, _products_by_id
    path = os.path.join(os.path.dirname(__file__), "..", settings.PRODUCT_CATALOGUE_PATH)
    path = os.path.normpath(path)
    _products = []
    _products_by_id = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("product_id", "").strip():
                p = Product(row)
                _products.append(p)
                _products_by_id[p.product_id] = p
    return _products


def get_all_products() -> List[Product]:
    return _products


def get_product_by_id(product_id: str) -> Optional[Product]:
    return _products_by_id.get(product_id)


def check_eligibility(
    product: Product,
    city_tier: int,
    employee_count: int,
    num_sites: int,
    has_gstin: bool,
    gstin_active: bool,
    bundle_product_ids: List[str],
    segment: Optional[str] = None,
) -> dict:
    """
    Returns {eligible: bool, reasons: [str]}
    All rules are deterministic from catalogue data.
    """
    reasons = []

    # Rule 1: City tier
    if city_tier not in product.available_tiers:
        reasons.append(f"Not available in Tier {city_tier} cities")

    # Rule 2: Min employees
    if employee_count < product.min_employees:
        reasons.append(f"Requires at least {product.min_employees} employees (you have {employee_count})")

    # Rule 3: Min sites
    if num_sites < product.min_sites:
        reasons.append(f"Requires at least {product.min_sites} sites (you have {num_sites})")

    # Rule 4: GSTIN required
    if product.requires_gstin:
        if not has_gstin or not gstin_active:
            reasons.append("Requires an active GSTIN")

    # Rule 5: Product dependencies
    if product.requires_one_of:
        if not any(pid in bundle_product_ids for pid in product.requires_one_of):
            reasons.append(
                f"Requires one of: {', '.join(product.requires_one_of)} in your bundle"
            )

    return {"eligible": len(reasons) == 0, "reasons": reasons}


def filter_eligible_products(
    city_tier: int,
    employee_count: int,
    num_sites: int,
    has_gstin: bool,
    gstin_active: bool,
    bundle_product_ids: List[str] = None,
    segment: Optional[str] = None,
) -> List[dict]:
    """Return all products with eligibility status for a given business profile."""
    bundle_product_ids = bundle_product_ids or []
    result = []
    for product in _products:
        eligibility = check_eligibility(
            product, city_tier, employee_count, num_sites,
            has_gstin, gstin_active, bundle_product_ids, segment
        )
        d = product.to_dict()
        d["eligible"] = eligibility["eligible"]
        d["ineligibility_reasons"] = eligibility["reasons"]
        result.append(d)
    return result
