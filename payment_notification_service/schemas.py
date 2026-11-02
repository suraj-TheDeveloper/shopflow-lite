from decimal import Decimal
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

class InitiatePaymentIn(BaseModel):
    order_id: int

class WebhookIn(BaseModel):
    order_id: int
    status: Literal["success", "failed"]
    transaction_id: str

class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_id: int
    amount: Decimal
    status: str

class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    message: str
    created_at: datetime