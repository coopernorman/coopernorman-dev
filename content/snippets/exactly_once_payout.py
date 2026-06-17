"""
ShareShark — exactly-once settlement  (ILLUSTRATIVE / SIMPLIFIED)

Three independent guards make a double-payout impossible even if settlement runs
twice (overlapping cron windows, a retry, or a future bug):

    (1) a cheap state short-circuit,
    (2) a re-check under the row lock,
    (3) a database UNIQUE constraint as the durable, race-proof backstop.

Guard (3) is the one that matters most: even if (1) and (2) are ever bypassed by
a code path no one anticipated, Postgres physically refuses the second payout row.
"""
from django.db import models, transaction, IntegrityError
from django.db.models import F, UniqueConstraint


class WalletTransaction(models.Model):
    wallet = models.ForeignKey("Wallet", on_delete=models.PROTECT)
    entry = models.ForeignKey("Entry", on_delete=models.PROTECT)
    transaction_type = models.CharField(max_length=32)        # e.g. "PAYOUT"
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            # The backstop: at most one PAYOUT per (wallet, entry). Enforced by the DB,
            # so correctness does not depend on the application getting it right.
            UniqueConstraint(
                fields=["wallet", "entry", "transaction_type"],
                name="uniq_txn_per_wallet_entry_type",
            )
        ]


def settle_entry(entry_id):
    with transaction.atomic():
        entry = Entry.objects.select_for_update().get(id=entry_id)

        # (1) cheap state guard — already settled?
        if not entry.active:
            return

        # (2) re-check under the lock — guards overlapping settlement runs
        if WalletTransaction.objects.filter(entry=entry, transaction_type="PAYOUT").exists():
            entry.active = False
            entry.save(update_fields=["active"])
            return

        try:
            # (3) the unique constraint is the final, race-proof guarantee
            WalletTransaction.objects.create(
                wallet=entry.user.wallet, entry=entry,
                transaction_type="PAYOUT", amount=entry.potential_payout,
            )
        except IntegrityError:
            # a concurrent worker already paid this entry — safe no-op
            return

        Wallet.objects.filter(user=entry.user).update(
            redeemable=F("redeemable") + entry.potential_payout
        )
        entry.active = False
        entry.save(update_fields=["active"])
