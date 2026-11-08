"""Quotes router: create, view, edit quotes and trigger simulated checkout."""
import json
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import Quote, Order, Business, KYCRecord
from app.services.pricing_service import calculate_quote, get_max_install_days_for_products
from app.services.catalogue_service import check_eligibility, get_product_by_id

router = APIRouter(prefix="/quotes", tags=["quotes"])


class LineItemRequest(BaseModel):
    product_id: str
    quantity: int = 1


class QuoteRequest(BaseModel):
    business_id: int
    line_items: List[LineItemRequest]
    city_tier: int = 2


class QuoteUpdateRequest(BaseModel):
    line_items: List[LineItemRequest]


@router.post("/")
def create_quote(req: QuoteRequest, db: Session = Depends(get_db)):
    """Create a new quote with deterministic pricing."""
    biz = db.query(Business).filter(Business.id == req.business_id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    # Validate eligibility for all products
    errors = []
    for item in req.line_items:
        p = get_product_by_id(item.product_id)
        if not p:
            errors.append(f"Product {item.product_id} not found")
            continue
        bundle_ids = [i.product_id for i in req.line_items if i.product_id != item.product_id]
        elig = check_eligibility(
            p,
            city_tier=biz.city_tier or req.city_tier,
            employee_count=biz.employee_count or 1,
            num_sites=biz.num_sites or 1,
            has_gstin=biz.has_gstin,
            gstin_active=biz.has_gstin,  # Simple: if they have GSTIN, treat as active
            bundle_product_ids=bundle_ids,
        )
        if not elig["eligible"]:
            errors.append(f"{p.product_name}: {'; '.join(elig['reasons'])}")

    if errors:
        raise HTTPException(status_code=400, detail={"message": "Eligibility check failed", "errors": errors})

    # Calculate pricing
    items_dict = [{"product_id": i.product_id, "quantity": i.quantity} for i in req.line_items]
    calc = calculate_quote(items_dict, city_tier=biz.city_tier or req.city_tier)

    quote = Quote(
        business_id=req.business_id,
        line_items_json=json.dumps(calc["line_items"]),
        total_monthly_inr=calc["total_monthly_inr"],
        total_setup_inr=calc["total_setup_inr"],
        contract_months=calc["recommended_contract_months"],
        status="DRAFT",
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)

    return {
        "quote_id": quote.id,
        "status": quote.status,
        **calc,
    }


@router.get("/{quote_id}")
def get_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    return {
        "quote_id": quote.id,
        "business_id": quote.business_id,
        "status": quote.status,
        "line_items": json.loads(quote.line_items_json),
        "total_monthly_inr": quote.total_monthly_inr,
        "total_setup_inr": quote.total_setup_inr,
        "contract_months": quote.contract_months,
        "created_at": quote.created_at.isoformat(),
    }


@router.put("/{quote_id}")
def update_quote(quote_id: int, req: QuoteUpdateRequest, db: Session = Depends(get_db)):
    """Update line items in a DRAFT quote."""
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Only DRAFT quotes can be edited")

    biz = db.query(Business).filter(Business.id == quote.business_id).first()
    items_dict = [{"product_id": i.product_id, "quantity": i.quantity} for i in req.line_items]
    calc = calculate_quote(items_dict, city_tier=biz.city_tier if biz else 2)

    quote.line_items_json = json.dumps(calc["line_items"])
    quote.total_monthly_inr = calc["total_monthly_inr"]
    quote.total_setup_inr = calc["total_setup_inr"]
    quote.contract_months = calc["recommended_contract_months"]
    db.commit()

    return {"quote_id": quote_id, "updated": True, **calc}


@router.post("/{quote_id}/checkout")
def checkout_quote(quote_id: int, db: Session = Depends(get_db)):
    """Accept a quote and create an order (simulated)."""
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != "DRAFT":
        raise HTTPException(status_code=400, detail="Quote already processed")

    # Check KYC status if business has GSTIN products
    line_items = json.loads(quote.line_items_json)
    product_ids = [item["product_id"] for item in line_items]
    max_install_days = get_max_install_days_for_products(product_ids)

    # Mark quote as accepted
    quote.status = "ACCEPTED"

    # Create order with initial timeline
    now = datetime.utcnow()
    timeline = [{"status": "Order Confirmed", "timestamp": now.isoformat(), "note": "Order confirmed by customer"}]

    order = Order(
        quote_id=quote.id,
        business_id=quote.business_id,
        status="Order Confirmed",
        typical_install_days=max_install_days,
        timeline_json=json.dumps(timeline),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "order_id": order.id,
        "quote_id": quote_id,
        "status": order.status,
        "typical_install_days": order.typical_install_days,
        "timeline": timeline,
        "note": "⚠️ This is a simulated order. Accel Business is not integrated with any real telecom system.",
    }
