from fastapi import FastAPI, Depends, HTTPException, dependencies
from sqlalchemy.orm import session, selectinload
from database import engine, Base, get_db
from models import Product, Orders, OrderItems
from service import get_current_user
from schemas import *
from decimal import Decimal
from sqlalchemy import select
from collections import defaultdict
from typing import Literal
from kafka_producer import publish_event, producer
import atexit
atexit.register(lambda: producer.flush(5))

Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/product")
def get_products(db: session = Depends(get_db), page: int = 1, limit: int = 10):
    offset = (page - 1) * limit
    data = db.query(Product).limit(limit).offset(offset).all()
    fetchedData = []
    for item in data:
        fetchedData.append(item)
    return { "status": 200, "message": "Product fetched successfully", "data": fetchedData, "page": page, "limit": limit }

@app.post("/cart/items", status_code=201)
def cart_items(data: OrderIn, db: session = Depends(get_db), user=Depends(get_current_user)):

    qty_by_product = defaultdict(int)
    for item in data.items:
        qty_by_product[item.product_id] += item.quantity

    cart = (
        db.query(Orders)
        .options(selectinload(Orders.items))
        .filter(Orders.user_id == user["id"], Orders.status == "cart")
        .first()
    )
    if not cart:
        cart = Orders(user_id=user["id"], status="cart", total_amount=Decimal("0"))
        db.add(cart)

    products = db.query(Product).filter(Product.id.in_(qty_by_product.keys())).all()
    product_map = {p.id: p for p in products}

    missing = set(qty_by_product) - set(product_map)
    if missing:
        raise HTTPException(404, f"Products not found: {sorted(missing)}")

    existing = {i.product_id: i for i in cart.items}
    for pid, qty in qty_by_product.items():
        product = product_map[pid]
        new_qty = qty + (existing[pid].quantity if pid in existing else 0)

        if product.stock < new_qty:
            raise HTTPException(409, f"Only {product.stock} of {product.name} in stock")

        if pid in existing:
            existing[pid].quantity = new_qty
            existing[pid].unit_price = product.price
        else:
            cart.items.append(OrderItems(
                product_id=pid,
                unit_price=product.price,
                quantity=qty,
            ))

    cart.total_amount = sum(
        (i.unit_price * i.quantity for i in cart.items), Decimal("0")
    )

    db.commit()
    db.refresh(cart)
    return {"message": "item added to cart", "order_id": cart.id, "total_amount": str(cart.total_amount)}

@app.get("/orders/{id}")
def order_items(id: int, db: session = Depends(get_db), user=Depends(get_current_user)):
    orders = db.query(Orders).filter(Orders.id == id).first()
    return { 
        "status": 200,  
        "message": "Order fetched successfully", 
        "data": {
            "order_id": orders.id,
            "user_id": orders.user_id,
            "total_amount": orders.total_amount,
            "status": orders.status,
            "items": [
                {
                    "id": item.id,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "line_total": item.unit_price * item.quantity,
                    "product": {
                        "id": item.product.id,
                        "name": item.product.name,
                    },
                }
                for item in orders.items
            ]
        } 
    }

@app.post("/orders/{order_id}/checkout")
def checkout(order_id:int, db: session = Depends(get_db), user=Depends(get_current_user)):
    order = (
        db.query(Orders)
        .options(selectinload(Orders.items))
        .filter(Orders.id == order_id, Orders.user_id == user["id"])
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != "cart":
        raise HTTPException(400, "Order already checked out")
    if not order.items:
        raise HTTPException(400, "Cart is empty")

    product_ids = sorted({i.product_id for i in order.items})
    products = db.scalars(
        select(Product)
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
    ).all()
    product_map = {p.id: p for p in products}

    total = Decimal("0")
    for item in order.items:
        product = product_map.get(item.product_id)
        if not product:
            raise HTTPException(404, f"Product {item.product_id} no longer exists")
        if product.stock < item.quantity:
            raise HTTPException(409, f"Insufficient stock for {product.name}")

        product.stock -= item.quantity
        item.unit_price = product.price
        total += product.price * item.quantity

    order.total_amount = total
    order.status = "pending_payment"
    db.commit()
    publish_event(
        "order.created",
        key=str(order.id),               # same order -> same partition -> ordered
        data={"order_id": order.id, "user_id": order.user_id, "amount": str(total)},
    )
    return {
        "message": "Checkout successful",
        "order_id": order.id,
        "status": order.status,
        "total_amount": str(total),
    }

class StatusIn(BaseModel):
    status: Literal["paid", "payment_failed"]

@app.put("/internal/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    data: StatusIn,
    db: session = Depends(get_db),
):
    order = (
        db.query(Orders)
        .options(selectinload(Orders.items).selectinload(OrderItems.product))
        .filter(Orders.id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != "pending_payment":
        return {"ok": True, "status": order.status}      # already handled

    order.status = data.status
    if data.status == "payment_failed":
        for item in order.items:                          # give reserved stock back
            item.product.stock += item.quantity
    db.commit()
    return {"ok": True, "status": order.status}