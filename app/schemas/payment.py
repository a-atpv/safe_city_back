from typing import List

from pydantic import BaseModel, Field


class CreatePaymentRequest(BaseModel):
    plan: str = Field(..., description="Plan code: 'monthly' | 'yearly'")
    recurring: bool = Field(True, description="Enable auto-renewal (recurring charges)")


class CreatePaymentResponse(BaseModel):
    payment_id: int
    inv_id: int
    amount: int            # in tiyn
    currency: str = "KZT"
    payment_url: str       # redirect the user here to pay


class PlanInfo(BaseModel):
    code: str
    title: str
    amount: int            # in tiyn
    currency: str = "KZT"
    period_months: int


class PlansResponse(BaseModel):
    plans: List[PlanInfo]
