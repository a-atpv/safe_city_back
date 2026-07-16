"""Robokassa payment endpoints: create invoice + handle callbacks.

Public (no auth) callbacks:
  POST/GET /payments/robokassa/result   -> source of truth, activates subscription, returns "OK<InvId>"
  POST/GET /payments/robokassa/success  -> user redirect after paying (UX only)
  POST/GET /payments/robokassa/fail     -> user redirect after cancel/failure
"""
import logging

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
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
from app.schemas.user import SubscriptionResponse
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


@router.post("/subscription/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel auto-renewal for the current user's subscription.

    Access is kept until the end of the paid period; only future recurring
    charges are stopped. This backs the in-app «Отменить подписку» form.
    """
    sub = await PaymentService.cancel_subscription(db, current_user.id)
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription to cancel",
        )
    return sub


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


def _app_return_html(success: bool, inv_id: Optional[str]) -> str:
    """Tiny page shown in the payment browser that bounces the user back into
    the mobile app via the custom scheme, with a manual fallback button.

    On Android the in-app WebView intercepts the /success|/fail navigation and
    never renders this; on iOS the SFSafariViewController renders it and the
    scheme redirect dismisses the sheet and foregrounds the app.
    """
    scheme = settings.payment_app_scheme or "safecity"
    kind = "success" if success else "fail"
    link = f"{scheme}://pay/{kind}" + (f"?inv_id={inv_id}" if inv_id else "")
    title = "Оплата прошла" if success else "Оплата не завершена"
    icon = "✓" if success else "✕"
    color = "#22C55E" if success else "#EF4444"
    style = (
        "<style>html,body{margin:0;height:100%;background:#0F172A;color:#F1F5F9;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}"
        ".wrap{display:flex;min-height:100%;align-items:center;justify-content:center;padding:24px}"
        ".card{max-width:360px;text-align:center}"
        ".icon{width:72px;height:72px;line-height:72px;border-radius:50%;margin:0 auto 20px;"
        "font-size:38px;color:#fff}h1{font-size:20px;margin:0 0 8px}"
        "p{color:#94A3B8;margin:0 0 24px;font-size:15px}"
        "a.btn{display:inline-block;background:#2563EB;color:#fff;text-decoration:none;"
        "padding:14px 28px;border-radius:12px;font-size:16px;font-weight:600}</style>"
    )
    # Plain concatenation (no f-string) so JS/CSS braces need no escaping.
    script = (
        '<script>var t="' + link + '";location.replace(t);'
        "setTimeout(function(){location.href=t},600);</script>"
    )
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Safe City</title>" + script + style
        + '</head><body><div class="wrap"><div class="card">'
        + f'<div class="icon" style="background:{color}">{icon}</div>'
        + f"<h1>{title}</h1><p>Возвращаемся в приложение…</p>"
        + f'<a class="btn" href="{link}">Вернуться в приложение</a>'
        + "</div></div></body></html>"
    )


def _finish(success: bool, inv_id: Optional[str]):
    """Web override (configured http redirect) wins; otherwise bounce to the app."""
    redirect = (
        settings.payment_success_redirect if success else settings.payment_fail_redirect
    )
    if redirect:
        return RedirectResponse(redirect, status_code=302)
    return HTMLResponse(_app_return_html(success, inv_id))


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
    """User is redirected here after paying. Activation happens on ResultURL, not
    here — this only returns the user to the app (or web redirect)."""
    data = await _params(request)
    out_sum = _pick(data, "OutSum", "outSum")
    inv_id = _pick(data, "InvId", "invId")
    signature = _pick(data, "SignatureValue", "crc")

    valid = bool(out_sum and inv_id and signature) and robokassa.verify_success_signature(
        out_sum, inv_id, signature
    )
    return _finish(valid, inv_id)


@router.api_route("/robokassa/fail", methods=["GET", "POST"])
async def robokassa_fail(request: Request, db: AsyncSession = Depends(get_db)):
    """User is redirected here after cancelling or a failed payment."""
    data = await _params(request)
    inv_id = _pick(data, "InvId", "invId")
    if inv_id:
        await PaymentService.mark_failed(db, inv_id)
    return _finish(False, inv_id)
