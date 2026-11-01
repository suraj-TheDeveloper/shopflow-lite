from fastapi import FastAPI, Depends, HTTPException, dependencies
from sqlalchemy.orm import session, selectinload
from database import engine, Base, get_db
from models import Product, Orders, OrderItems
from service import get_current_user
from schemas import *
from decimal import Decimal
from sqlalchemy import select

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
    order = Orders(user_id=user["id"], total_amount=Decimal("0"))
    total = Decimal("0")

    for item in data.items:
        product = db.get(Product, item.product_id)
        if not product:
            raise HTTPException(404, f"Product {item.product_id} not found")

        total += product.price * item.quantity
        order.items.append(OrderItems(
            product_id=product.id,
            unit_price=product.price,
            quantity=item.quantity,
        ))

    order.total_amount = total
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"message": "item added to cart", "order_id": order.id}

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

    return {
        "message": "Checkout successful",
        "order_id": order.id,
        "status": order.status,
        "total_amount": str(total),
    }