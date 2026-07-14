"""Scheduled subscription maintenance — run once a day (Heroku Scheduler).

    python -m app.jobs.subscriptions             # live
    python -m app.jobs.subscriptions --dry-run   # log intended actions, change nothing

Two passes, both idempotent and safe to run more than once a day:
  1. renew  — charge recurring child payments for Robokassa subs nearing expiry
              (capture is confirmed later on ResultURL, which extends the sub).
  2. expire — flip Robokassa subs to EXPIRED once past the renewal retry window.
"""
import argparse
import asyncio
import logging

from app.core.database import async_session
from app.services.payment import PaymentService

logger = logging.getLogger("app.jobs.subscriptions")


async def run(dry_run: bool = False) -> dict:
    async with async_session() as db:
        renew = await PaymentService.renew_due_subscriptions(db, dry_run=dry_run)
        expire = await PaymentService.expire_lapsed_subscriptions(db, dry_run=dry_run)
    result = {"dry_run": dry_run, "renew": renew, "expire": expire}
    logger.info("subscriptions job done: %s", result)
    return result


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Subscription renewal + expiry job")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without charging or changing the DB.",
    )
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
