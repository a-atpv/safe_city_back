"""Subscription plans catalog.

Prices are in tiyn (1 KZT = 100 tiyn), matching Payment.amount / Subscription.price.

NOTE: the prices below are PLACEHOLDERS — confirm the real tariffs with the
business before go-live. Changing a price here is a one-line edit.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    code: str            # short id: "monthly" | "yearly"
    title: str           # human title, used in the payment description and fiscal receipt
    price_tiyn: int      # price in tiyn (1 KZT = 100 tiyn)
    period_months: int   # subscription length in calendar months


PLANS: dict[str, Plan] = {
    "monthly": Plan(
        code="monthly",
        title="Подписка Safe City — 1 месяц",
        price_tiyn=80_000,    # 800 ₸ (source: safe-city.kz)
        period_months=1,
    ),
    "yearly": Plan(
        code="yearly",
        title="Подписка Safe City — 1 год",
        price_tiyn=690_000,   # 6 900 ₸ (source: safe-city.kz)
        period_months=12,
    ),
}


def get_plan(code: str) -> Plan | None:
    return PLANS.get(code)
