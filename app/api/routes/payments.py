"""Robokassa payment endpoints: create invoice + handle callbacks.

Public (no auth) callbacks:
  POST/GET /payments/robokassa/result   -> source of truth, activates subscription, returns "OK<InvId>"
  POST/GET /payments/robokassa/success  -> user redirect after paying (UX only)
  POST/GET /payments/robokassa/fail     -> user redirect after cancel/failure
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core import get_db, settings
from app.core.plans import PLANS, get_plan
from app.models import User
from app.schemas.payment import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    PlanInfo,
    PlansResponse,
)
from app.services import robokassa
from app.services.payment import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get("/plans", response_model=PlansResponse)
async def list_plans():
    """Public catalog of subscription plans."""
    return PlansResponse(
        plans=[
            PlanInfo(
                code=p.code,
                title=p.title,
                amount=p.price_tiyn,
                currency="KZT",
                period_months=p.period_months,
            )
            for p in PLANS.values()
        ]
    )


@router.post("/create", response_model=CreatePaymentResponse)
async def create_payment(
    data: CreatePaymentRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a pending payment and return the Robokassa payment URL."""
    if get_plan(data.plan) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown plan")
    try:
        payment, url = await PaymentService.create_subscription_payment(
            db, current_user, data.plan, data.recurring
        )
    except RuntimeError as e:  # Robokassa credentials not configured
        logger.error("Payment create failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment provider is not configured",
        )
    return CreatePaymentResponse(
        payment_id=payment.id,
        inv_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        payment_url=url,
    )


async def _params(request: Request) -> dict:
    """Merge query-string and form-body params (Robokassa may use either)."""
    data = dict(request.query_params)
    if request.method == "POST":
        try:
            form = await request.form()
            data.update({k: str(v) for k, v in form.items()})
        except Exception:
            pass
    return data


def _pick(data: dict, *names: str):
    for n in names:
        if data.get(n) not in (None, ""):
            return data[n]
    return None


@router.api_route("/robokassa/result", methods=["GET", "POST"])
async def robokassa_result(request: Request, db: AsyncSession = Depends(get_db)):
    """Server-to-server payment notification. Must return exactly 'OK<InvId>'."""
    data = await _params(request)
    out_sum = _pick(data, "OutSum", "outSum", "out_summ")
    inv_id = _pick(data, "InvId", "invId", "inv_id")
    signature = _pick(data, "SignatureValue", "crc")
    if not (out_sum and inv_id and signature):
        return PlainTextResponse("bad request", status_code=400)

    payment = await PaymentService.handle_successful_result(db, out_sum, inv_id, signature)
    if payment is None:
        return PlainTextResponse("bad sign", status_code=400)
    return PlainTextResponse(f"OK{inv_id}")


@router.api_route("/robokassa/success", methods=["GET", "POST"])
async def robokassa_success(request: Request):
    """User is redirected here after paying. Activation happens on ResultURL, not here."""
    data = await _params(request)
    out_sum = _pick(data, "OutSum", "outSum")
    inv_id = _pick(data, "InvId", "invId")
    signature = _pick(data, "SignatureValue", "crc")

    valid = bool(out_sum and inv_id and signature) and robokassa.verify_success_signature(
        out_sum, inv_id, signature
    )
    if not valid:
        if settings.payment_fail_redirect:
            return RedirectResponse(settings.payment_fail_redirect, status_code=302)
        return PlainTextResponse("bad sign", status_code=400)

    if settings.payment_success_redirect:
        return RedirectResponse(settings.payment_success_redirect, status_code=302)
    return {"status": "success", "inv_id": inv_id}


@router.api_route("/robokassa/fail", methods=["GET", "POST"])
async def robokassa_fail(request: Request, db: AsyncSession = Depends(get_db)):
    """User is redirected here after cancelling or a failed payment."""
    data = await _params(request)
    inv_id = _pick(data, "InvId", "invId")
    if inv_id:
        await PaymentService.mark_failed(db, inv_id)
    if settings.payment_fail_redirect:
        return RedirectResponse(settings.payment_fail_redirect, status_code=302)
    return {"status": "fail", "inv_id": inv_id}
