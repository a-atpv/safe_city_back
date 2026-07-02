"""Robokassa (Kazakhstan) payment protocol helpers.

Pure protocol layer — signatures, payment URL, fiscal receipt, and callback
verification. No database access here. Docs: https://docs.robokassa.kz/

Signature formulas (hash algo is configurable and MUST match the shop cabinet):
  init:     MerchantLogin:OutSum:InvId[:Receipt]:Password#1     -> payment link
  result:   OutSum:InvId:Password#2                             -> ResultURL callback
  success:  OutSum:InvId:Password#1                             -> SuccessURL redirect

Amounts are stored in tiyn (int) everywhere in the app and converted to the
tenge OutSum string ("1500.00") only at the Robokassa boundary.
"""
import hashlib
import hmac
import json
import logging
import urllib.parse
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_SUPPORTED_ALGOS = {"md5", "sha1", "sha256", "sha384", "sha512"}


def _algo() -> str:
    algo = (settings.robokassa_hash_algo or "sha256").lower()
    return algo if algo in _SUPPORTED_ALGOS else "sha256"


def _hash(data: str) -> str:
    h = hashlib.new(_algo())
    h.update(data.encode("utf-8"))
    return h.hexdigest()


def _require(*attrs: str) -> None:
    missing = [a for a in attrs if not getattr(settings, a, None)]
    if missing:
        raise RuntimeError(f"Robokassa is not configured: missing {', '.join(missing)}")


def amount_to_outsum(amount_tiyn: int) -> str:
    """150000 tiyn -> '1500.00'. Canonical OutSum string (tenge, 2 decimals)."""
    tenge = (Decimal(amount_tiyn) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{tenge:.2f}"


def amounts_equal(out_sum: str, amount_tiyn: int) -> bool:
    """True if a callback OutSum matches the expected tiyn amount (format-agnostic)."""
    try:
        return Decimal(out_sum) == (Decimal(amount_tiyn) / 100).quantize(Decimal("0.01"))
    except Exception:
        return False


def build_receipt(item_name: str, amount_tiyn: int, vat: Optional[str] = None) -> str:
    """Return the RAW (non-encoded) single-item fiscal Receipt JSON string.

    Robokassa signs the *raw* JSON and expects it URL-encoded once for transport
    (verified against the live test form — variant "V1"). The caller encodes it
    for the GET URL, or lets the HTTP client form-encode it for the recurring POST.
    """
    tenge = float((Decimal(amount_tiyn) / 100).quantize(Decimal("0.01")))
    receipt = {
        "items": [
            {
                "name": item_name[:128],
                "quantity": 1,
                "sum": tenge,
                "payment_method": "full_payment",
                "payment_object": "service",
                "tax": vat or settings.robokassa_vat or "none",
            }
        ]
    }
    return json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))


def calc_init_signature(out_sum: str, inv_id: int, receipt: Optional[str] = None) -> str:
    """init signature: hash(MerchantLogin:OutSum:InvId[:Receipt]:Password#1).

    Receipt, when present, is the RAW (non-encoded) JSON — see build_receipt.
    """
    _require("robokassa_merchant_login", "robokassa_password1")
    parts = [settings.robokassa_merchant_login, out_sum, str(inv_id)]
    if receipt:
        parts.append(receipt)
    parts.append(settings.robokassa_password1)
    return _hash(":".join(parts))


def build_payment_url(
    *,
    inv_id: int,
    amount_tiyn: int,
    description: str,
    email: Optional[str] = None,
    recurring: bool = False,
    receipt_name: Optional[str] = None,
    is_test: Optional[bool] = None,
) -> str:
    """Build the redirect URL to the Robokassa payment page for one invoice."""
    _require("robokassa_merchant_login")
    out_sum = amount_to_outsum(amount_tiyn)
    receipt_json = build_receipt(receipt_name, amount_tiyn) if receipt_name else None
    signature = calc_init_signature(out_sum, inv_id, receipt_json)

    params = {
        "MerchantLogin": settings.robokassa_merchant_login,
        "OutSum": out_sum,
        "InvId": str(inv_id),
        "Description": description,
        "SignatureValue": signature,
        "Culture": "ru",
        "Encoding": "utf-8",
    }
    if email:
        params["Email"] = email
    if recurring:
        # Marks this as the "parent" payment so the card can be charged again later.
        params["Recurring"] = "true"
    is_test = settings.robokassa_is_test if is_test is None else is_test
    if is_test:
        params["IsTest"] = "1"

    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    if receipt_json:
        # Sign the raw JSON; transmit it URL-encoded exactly once.
        query = f"{query}&Receipt={urllib.parse.quote(receipt_json, safe='')}"
    return f"{settings.robokassa_payment_url}?{query}"


def _verify(out_sum: str, inv_id: str, signature: str, password_attr: str) -> bool:
    _require(password_attr)
    expected = _hash(f"{out_sum}:{inv_id}:{getattr(settings, password_attr)}")
    return hmac.compare_digest(expected.lower(), (signature or "").lower())


def verify_result_signature(out_sum: str, inv_id: str, signature: str) -> bool:
    """Verify a ResultURL callback signature (Password #2)."""
    return _verify(out_sum, str(inv_id), signature, "robokassa_password2")


def verify_success_signature(out_sum: str, inv_id: str, signature: str) -> bool:
    """Verify a SuccessURL redirect signature (Password #1)."""
    return _verify(out_sum, str(inv_id), signature, "robokassa_password1")


async def charge_recurring(
    *,
    inv_id: int,
    previous_inv_id: int,
    amount_tiyn: int,
    description: str,
    receipt_name: Optional[str] = None,
) -> str:
    """Charge a recurring (child) payment against a stored card. [Phase 3 primitive]

    NB: a returned 'OK<InvId>' means the operation was *created*, not that funds
    were captured — the real result arrives asynchronously on ResultURL.
    PreviousInvoiceID is intentionally excluded from the signature.
    """
    import httpx

    _require("robokassa_merchant_login")
    out_sum = amount_to_outsum(amount_tiyn)
    receipt_json = build_receipt(receipt_name, amount_tiyn) if receipt_name else None
    signature = calc_init_signature(out_sum, inv_id, receipt_json)

    data = {
        "MerchantLogin": settings.robokassa_merchant_login,
        "InvoiceID": str(inv_id),
        "PreviousInvoiceID": str(previous_inv_id),
        "OutSum": out_sum,
        "Description": description,
        "SignatureValue": signature,
    }
    if receipt_json:
        data["Receipt"] = receipt_json  # httpx form-encodes it once

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(settings.robokassa_recurring_url, data=data)
        logger.info(
            "Robokassa recurring charge inv=%s prev=%s -> %s %s",
            inv_id, previous_inv_id, resp.status_code, resp.text,
        )
        resp.raise_for_status()
        return resp.text
