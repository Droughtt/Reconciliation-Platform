from django.db import transaction

from imports.models import BankTransaction, ImportBatch, LedgerEntry

from .engine import Txn, reconcile
from .models import Flag, MatchResult, ReconciliationRun


class RunInputError(Exception):
    """The requested batches can't be reconciled."""


def _to_txns(queryset):
    return [
        Txn(id=r.id, reference=r.reference, txn_date=r.txn_date, amount=r.amount)
        for r in queryset
    ]


def _get_batch(batch_id, kind):
    try:
        batch = ImportBatch.objects.get(pk=batch_id, kind=kind)
    except ImportBatch.DoesNotExist:
        raise RunInputError(f"No {kind} batch with id {batch_id}.")
    if batch.status != ImportBatch.Status.COMPLETED:
        raise RunInputError(f"Batch {batch_id} has no usable rows (status: {batch.status}).")
    return batch


def run_reconciliation(*, bank_batch_id, ledger_batch_id, user, date_window_days=5):
    bank_batch = _get_batch(bank_batch_id, ImportBatch.Kind.BANK)
    ledger_batch = _get_batch(ledger_batch_id, ImportBatch.Kind.LEDGER)

    bank = _to_txns(BankTransaction.objects.filter(batch=bank_batch))
    ledger = _to_txns(LedgerEntry.objects.filter(batch=ledger_batch))
    outcomes = reconcile(bank, ledger, date_window_days)

    with transaction.atomic():
        run = ReconciliationRun.objects.create(
            created_by=user, bank_batch=bank_batch, ledger_batch=ledger_batch
        )
        MatchResult.objects.bulk_create(
            [
                MatchResult(
                    run=run,
                    bank_txn_id=o.bank_id,
                    ledger_entry_id=o.ledger_id,
                    status=o.status,
                    confidence=o.confidence,
                    amount_difference=o.amount_difference,
                    reason=o.reason,
                )
                for o in outcomes
            ],
            batch_size=1000,
        )
        # MySQL doesn't return ids from bulk_create, so re-query to attach flags
        to_review = MatchResult.objects.filter(run=run).exclude(status=MatchResult.Status.MATCHED)
        Flag.objects.bulk_create([Flag(result=r) for r in to_review], batch_size=1000)
    return run