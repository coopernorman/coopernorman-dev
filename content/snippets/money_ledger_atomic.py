"""
ShareShark — concurrency-safe entry placement  (ILLUSTRATIVE / SIMPLIFIED)

This is a sanitized, simplified illustration of the real pattern — no secrets, no PII.
The point a reviewer should take away:

    Take the row lock FIRST, then compute every exposure-cap aggregate INSIDE the
    lock. That is what closes the classic "check-then-act" race where two concurrent
    requests each read "there's room under the cap" and both write, breaching it.
"""
from django.db import transaction
from django.db.models import Sum


def place_entry(user, stock, side, stake, potential_payout):
    with transaction.atomic():
        # 1) Serialize this user's concurrent placements on their wallet row.
        #    A second request for the same wallet blocks here until we commit.
        wallet = Wallet.objects.select_for_update().get(user=user)

        # 2) Compute caps INSIDE the lock (not before it). This is the fix —
        #    the aggregates can't go stale between the check and the write.
        user_stock_exposure = (
            Entry.objects.filter(user=user, stock=stock, side=side, active=True)
            .aggregate(t=Sum("potential_payout"))["t"] or 0
        )
        platform_exposure = (
            Entry.objects.filter(stock=stock, side=side, active=True)
            .aggregate(t=Sum("potential_payout"))["t"] or 0
        )

        # 3) Enforce every limit while still holding the lock.
        if wallet.redeemable < stake:
            raise InsufficientFunds()
        if user_stock_exposure + potential_payout > USER_STOCK_CAP:
            raise CapExceeded("per-user / per-stock")
        if platform_exposure + potential_payout > PLATFORM_LIABILITY_CAP:
            raise CapExceeded("platform liability")

        # 4) Debit + create the entry atomically. Commit releases the lock.
        wallet.redeemable -= stake
        wallet.save(update_fields=["redeemable"])
        return Entry.objects.create(
            user=user, stock=stock, side=side,
            stake=stake, potential_payout=potential_payout, active=True,
        )
