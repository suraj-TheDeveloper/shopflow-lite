from pydantic import BaseModel, Field

class OrderItemIn(BaseModel):
    product_id: int
    quantity: int
    
class OrderIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1)