import csv
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Abs

from imports.models import BankTransaction, LedgerEntry
from reconciliation.models import Flag, MatchResult

ZERO = Decimal("0.00")
OPEN_FLAG_STATUSES = [Flag.Status.NEEDS_REVIEW, Flag.Status.ESCALATED]

CSV_COLUMNS = [
    "result_id", "status", "confidence", "bank_reference", "bank_date", "bank_amount",
    "ledger_reference", "ledger_date", "ledger_amount", "amount_difference",
    "reason", "flag_status", "reviewed_by", "notes",
]


def _total(model, batch):
    return model.objects.filter(batch=batch).aggregate(t=Sum("amount"))["t"] or ZERO


def _batch_info(batch):
    return {
        "id": batch.id,
        "file": batch.original_filename,
        "total_rows": batch.total_rows,
        "imported_rows": batch.imported_rows,
        "failed_rows": batch.failed_rows,
    }


def build_summary(run):
    results = MatchResult.objects.filter(run=run)
    flags = Flag.objects.filter(result__run=run)

    by_status = {r["status"]: r["n"] for r in results.values("status").annotate(n=Count("id"))}
    flag_counts = {r["status"]: r["n"] for r in flags.values("status").annotate(n=Count("id"))}

    mismatches = results.filter(status=MatchResult.Status.AMOUNT_MISMATCH).aggregate(
        net=Sum("amount_difference"), gross=Sum(Abs("amount_difference"))
    )
    bank_total = _total(BankTransaction, run.bank_batch)
    ledger_total = _total(LedgerEntry, run.ledger_batch)

    return {
        "run_id": run.id,
        "created_at": run.created_at,
        "created_by": run.created_by.username,
        "bank_file": _batch_info(run.bank_batch),
        "ledger_file": _batch_info(run.ledger_batch),
        "results_by_status": by_status,
        "flags_by_status": flag_counts,
        "open_flags": flags.filter(status__in=OPEN_FLAG_STATUSES).count(),
        "totals": {
            "bank_total": str(bank_total),
            "ledger_total": str(ledger_total),
            "net_difference": str(bank_total - ledger_total),
            "amount_mismatch_net": str(mismatches["net"] or ZERO),
            "amount_mismatch_gross": str(mismatches["gross"] or ZERO),
        },
    }


def _safe(value):
    """Stop spreadsheet formula injection: text starting with = + - @ gets a leading quote."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def write_results_csv(run, stream, status=None):
    results = (
        MatchResult.objects.filter(run=run)
        .select_related("bank_txn", "ledger_entry", "flag__reviewed_by")
        .order_by("id")
    )
    if status:
        results = results.filter(status=status)

    writer = csv.writer(stream)
    writer.writerow(CSV_COLUMNS)
    for r in results:
        bank, ledger = r.bank_txn, r.ledger_entry
        flag = getattr(r, "flag", None)
        writer.writerow([
            r.id,
            r.status,
            r.confidence,
            _safe(bank.reference) if bank else "",
            bank.txn_date if bank else "",
            bank.amount if bank else "",
            _safe(ledger.reference) if ledger else "",
            ledger.txn_date if ledger else "",
            ledger.amount if ledger else "",
            r.amount_difference if r.amount_difference is not None else "",
            _safe(r.reason),
            flag.status if flag else "",
            flag.reviewed_by.username if flag and flag.reviewed_by else "",
            _safe(flag.notes) if flag else "",
        ])
        