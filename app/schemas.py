from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=6)
    workspace_name: str = Field(..., min_length=2)


class LoginRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str


class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = None
    billing_email: Optional[str] = Field(None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    tax_id: Optional[str] = None
    country: Optional[str] = None


class ChangePlanRequest(BaseModel):
    plan_id: str
    interval: str = Field("month", pattern="^(month|year)$")


class CancelSubscriptionRequest(BaseModel):
    at_period_end: bool = True


class TopUpCreditsRequest(BaseModel):
    credits: int


class RecordUsageRequest(BaseModel):
    metric: str = Field(..., pattern="^(api_calls|exports|ai_tokens)$")
    quantity: int = Field(..., ge=1)


class ClockAdvanceRequest(BaseModel):
    days: int = Field(..., ge=1, le=400)


class PaymentMethodCreateRequest(BaseModel):
    brand: str = Field(..., min_length=2)
    last4: str = Field(..., min_length=4, max_length=4)
    exp_month: int = Field(..., ge=1, le=12)
    exp_year: int = Field(..., ge=2024, le=2040)


class CreditAdjustRequest(BaseModel):
    delta: int
    reason: str
