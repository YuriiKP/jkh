from typing import Optional

from pydantic import BaseModel, Field


class YooKassaPayment(BaseModel):
    """Модель платежа от ЮKassa"""

    id: str = Field(..., alias="id")
    status: str = Field(..., alias="status")
    amount: dict = Field(..., alias="amount")
    description: Optional[str] = Field(None, alias="description")
    metadata: Optional[dict] = Field(None, alias="metadata")
    recipient: Optional[dict] = Field(None, alias="recipient")
    created_at: str = Field(..., alias="created_at")
    captured_at: Optional[str] = Field(None, alias="captured_at")
    payment_method: Optional[dict] = Field(None, alias="payment_method")
    test: bool = Field(False, alias="test")


class YooKassaWebhook(BaseModel):
    """Модель вебхука от ЮKassa"""

    type: str = Field(..., alias="type")
    event: str = Field(..., alias="event")
    object: YooKassaPayment = Field(..., alias="object")
