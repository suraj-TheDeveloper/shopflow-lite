from sqlalchemy import String, Integer, Column, Boolean, DateTime, func, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    price = Column(Integer)
    stock = Column(Integer)
    items = relationship("OrderItems", back_populates="product")

class Orders(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="cart", index=True)
    total_amount = Column(Numeric(10, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    items = relationship("OrderItems", back_populates="order", cascade="all, delete-orphan")

class OrderItems(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)
    order = relationship("Orders", back_populates="items")
    product = relationship("Product", back_populates="items")