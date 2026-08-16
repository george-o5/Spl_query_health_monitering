# Pydantic models
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class OrderBase(BaseModel):
    id: str
    quantity: float
    timestamp: datetime


class OrderCreate(OrderBase):
    pass


class Order(OrderBase):
    status: str

    class Config:
        from_attributes = True
