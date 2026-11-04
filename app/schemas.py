from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ProductCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = None
    price: int = Field(..., gt=0)
    compare_at_price: Optional[int] = None
    image_url: Optional[str] = None
    stock: int = Field(default=10, ge=0)

class ProductResponse(ProductCreate):
    id: int
    merchant_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class DeliveryZoneCreate(BaseModel):
    name: str = Field(..., min_length=2)
    fee: int = Field(..., ge=0)
    estimated_time: Optional[str] = "2h - 4h"

class OrderItemInput(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)

class CheckoutRequest(BaseModel):
    store_slug: str
    customer_name: str
    customer_phone: str
    delivery_zone_name: str
    delivery_address: str
    customer_notes: Optional[str] = None
    payment_method: str = "WAVE" # WAVE, ORANGE_MONEY, MTN_MOMO, MOOV
    items: List[OrderItemInput]

class MerchantSettingsUpdate(BaseModel):
    store_name: str
    name: str
    bio: Optional[str] = None
    wave_number: Optional[str] = None
    orange_money_number: Optional[str] = None
    mtn_momo_number: Optional[str] = None
    deposit_policy: str
    fixed_deposit_amount: Optional[int] = 2000
    deposit_percentage: Optional[int] = 30
