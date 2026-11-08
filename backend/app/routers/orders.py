"""Orders router: view orders and advance simulated status timeline."""
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import Order

router = APIRouter(prefix="/orders", tags=["orders"])

ORDER_TIMELINE = [
    "Order Confirmed",
    "KYC Verified",
    "Order Approved",
    "Fiber Dispatched",
    "Engineer Scheduled",
    "Installation",
    "Activated",
]


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    timeline = json.loads(order.timeline_json)
    current_idx = ORDER_TIMELINE.index(order.status) if order.status in ORDER_TIMELINE else 0

    return {
        "order_id": order.id,
        "quote_id": order.quote_id,
        "business_id": order.business_id,
        "status": order.status,
        "typical_install_days": order.typical_install_days,
        "timeline": timeline,
        "timeline_steps": [
            {
                "step": step,
                "completed": i <= current_idx,
                "current": i == current_idx,
                "timestamp": next(
                    (t["timestamp"] for t in timeline if t["status"] == step), None
                )
            }
            for i, step in enumerate(ORDER_TIMELINE)
        ],
        "created_at": order.created_at.isoformat(),
        "simulated": True,
        "disclaimer": "⚠️ Order status updates are simulated for demo purposes. This system is not integrated with any real telecom network."
    }


@router.post("/{order_id}/advance")
def advance_order_status(order_id: int, db: Session = Depends(get_db)):
    """
    Advance order to the next status in the timeline (simulated).
    For demo/testing purposes only.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == "Activated":
        raise HTTPException(status_code=400, detail="Order already fully activated")

    current_idx = ORDER_TIMELINE.index(order.status) if order.status in ORDER_TIMELINE else 0
    next_status = ORDER_TIMELINE[current_idx + 1]

    timeline = json.loads(order.timeline_json)
    timeline.append({
        "status": next_status,
        "timestamp": datetime.utcnow().isoformat(),
        "note": f"[SIMULATED] Status advanced to {next_status}"
    })

    order.status = next_status
    order.timeline_json = json.dumps(timeline)
    db.commit()

    return {
        "order_id": order_id,
        "new_status": next_status,
        "simulated": True,
        "timeline": timeline,
    }


@router.get("/business/{business_id}")
def get_orders_for_business(business_id: int, db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.business_id == business_id).all()
    return {
        "business_id": business_id,
        "orders": [
            {
                "order_id": o.id,
                "status": o.status,
                "typical_install_days": o.typical_install_days,
                "created_at": o.created_at.isoformat(),
            }
            for o in orders
        ]
    }
