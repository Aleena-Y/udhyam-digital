"""Recommendations router: returns eligible products for a business profile."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.services.catalogue_service import filter_eligible_products, get_all_products

router = APIRouter(prefix="/recommend", tags=["recommendations"])


class BusinessProfile(BaseModel):
    city_tier: int = 2
    employee_count: int = 1
    num_sites: int = 1
    has_gstin: bool = False
    gstin_active: bool = False
    bundle_product_ids: List[str] = []
    segment: Optional[str] = None
    products_of_interest: Optional[List[str]] = None


@router.post("/")
def get_recommendations(profile: BusinessProfile):
    """
    Return all products with eligibility status for a given business profile.
    Business rules are enforced deterministically — LLM never overrides these.
    """
    products = filter_eligible_products(
        city_tier=profile.city_tier,
        employee_count=profile.employee_count,
        num_sites=profile.num_sites,
        has_gstin=profile.has_gstin,
        gstin_active=profile.gstin_active,
        bundle_product_ids=profile.bundle_product_ids,
        segment=profile.segment,
    )

    eligible = [p for p in products if p["eligible"]]
    ineligible = [p for p in products if not p["eligible"]]

    # Highlight products of interest
    if profile.products_of_interest:
        for p in products:
            p["of_interest"] = p["product_id"] in profile.products_of_interest

    return {
        "eligible_count": len(eligible),
        "total_products": len(products),
        "products": products,
        "eligible": eligible,
        "ineligible": ineligible,
        "profile_used": profile.dict(),
    }


@router.get("/catalogue")
def get_catalogue():
    """Return all products in the catalogue (without eligibility filtering)."""
    return {
        "products": [p.to_dict() for p in get_all_products()],
        "count": len(get_all_products())
    }


@router.get("/categories")
def get_categories():
    """Return unique product categories."""
    products = get_all_products()
    cats = sorted(set(p.category for p in products))
    return {"categories": cats}
