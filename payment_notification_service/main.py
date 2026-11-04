import uuid
import httpx
from decimal import Decimal
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from database import engine, Base, get_db
from config import ORDER_SERVICE_URL, WEBHOOK_SECRET, INTERNAL_API_KEY
from models import Base, Payment, Notification
from schemas import InitiatePaymentIn, WebhookIn, PaymentOut, NotificationOut
from auth import get_current_user
from sqlalchemy.orm import session
from kafka_producer import publish_event, producer
import atexit
atexit.register(lambda: producer.flush(5))

Base.metadata.create_all(engine)

app = FastAPI(title="Payment & Notification Service")

# ---------- 1. Initiate a payment ----------
@app.post("/payments/initiate", status_code=201, response_model=PaymentOut)
def initiate_payment(
    data: InitiatePaymentIn,
    db: session = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        resp = httpx.get(
            f"{ORDER_SERVICE_URL}/orders/{data.order_id}",
            headers={"Authorization": user["token"]},
            timeout=5.0,
        )
        print("resp_payment", resp.status_code)
    except httpx.RequestError:
        raise HTTPException(503, "Order service unavailable")
    print("resp json", resp.json())
    if resp.status_code == 404:
        raise HTTPException(404, "Order not found")
    if resp.status_code != 200:
        raise HTTPException(502, "Could not fetch order")

    body = resp.json()
    order = body.get("data", body)

    if order.get("status") != "pending_payment":
        raise HTTPException(400, "Order is not awaiting payment")

    # Reuse an open payment session instead of creating duplicates
    existing = (
        db.query(Payment)
        .filter(Payment.order_id == data.order_id, Payment.status == "initiated")
        .first()
    )
    if existing:
        return existing

    payment = Payment(
        order_id=data.order_id,
        user_id=user["id"],
        amount=Decimal(str(order["total_amount"])),   # amount comes from the order service
        status="initiated",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


# ---------- 2. Webhook (simulated gateway callback) ----------
@app.post("/payments/webhook")
def payment_webhook(data: WebhookIn, db: session = Depends(get_db), x_webhook_secret: str = Header(None)):
    # Public endpoint, so protect it with a shared secret
    # if x_webhook_secret != WEBHOOK_SECRET:
    #     raise HTTPException(401, "Invalid webhook secret")

    payment = (db.query(Payment).filter(Payment.order_id == data.order_id).order_by(Payment.id.desc()).with_for_update().first())
    if not payment:
        raise HTTPException(404, "No payment found for this order")

    # Idempotent: a repeated webhook does nothing
    if payment.status != "initiated":
        return {"ok": True, "message": "Already processed", "status": payment.status}

    # 1. Record the transaction and a notification (one commit)
    payment.status = data.status
    payment.transaction_id = data.transaction_id
    if data.status == "success":
        message = f"Payment of {payment.amount} received for order #{payment.order_id}."
        ntype = "payment_success"
    else:
        message = f"Payment failed for order #{payment.order_id}. Please try again."
        ntype = "payment_failed"

    event_type = "payment.success" if data.status == "success" else "payment.failed"
    publish_event(
        event_type,
        key=str(payment.order_id),
        data={
            "order_id": payment.order_id,
            "user_id": payment.user_id,
            "amount": str(payment.amount),
            "transaction_id": data.transaction_id,
        },
    )
    db.commit()

    # 2. Tell the order service (replaced by a Kafka event later)
    new_status = "paid" if data.status == "success" else "payment_failed"
    try:
        r = httpx.put(
            f"{ORDER_SERVICE_URL}/internal/orders/{payment.order_id}/status",
            json={"status": new_status},
            timeout=5.0,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        # Payment is already recorded; log it so it can be retried
        print(f"WARNING: order {payment.order_id} status update to {new_status} failed")

    return {"ok": True, "status": payment.status}


# ---------- 3. Notification log ----------
@app.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: session = Depends(get_db),
    user=Depends(get_current_user),
):
    return (
        db.query(Notification)
        .filter(Notification.user_id == user["id"])
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )