from datetime import date
from decimal import Decimal

from reconciliation.engine import Txn, reconcile

D = date(2026, 10, 1)


def t(id, ref, amount, d=D):
    return Txn(id=id, reference=ref, txn_date=d, amount=Decimal(str(amount)))


def statuses(outcomes):
    return sorted(o.status for o in outcomes)


def test_exact_match():
    out = reconcile([t(1, "INV-1", 500)], [t(10, "INV-1", 500)])
    assert statuses(out) == ["matched"]
    assert out[0].confidence == 100
    assert (out[0].bank_id, out[0].ledger_id) == (1, 10)


def test_amount_mismatch_reports_difference():
    out = reconcile([t(1, "INV-1", "48500.00")], [t(10, "INV-1", "50000.00")])
    assert statuses(out) == ["amount_mismatch"]
    assert out[0].amount_difference == Decimal("-1500.00")


def test_date_mismatch_inside_window():
    out = reconcile([t(1, "INV-1", 500, date(2026, 10, 3))], [t(10, "INV-1", 500)])
    assert statuses(out) == ["date_mismatch"]


def test_date_outside_window_is_not_matched():
    out = reconcile([t(1, "INV-1", 500, date(2026, 11, 15))], [t(10, "INV-1", 500)])
    assert statuses(out) == ["unmatched_bank", "unmatched_ledger"]


def test_unmatched_on_each_side():
    out = reconcile([t(1, "A", 100)], [t(10, "B", 999, date(2027, 1, 1))])
    assert statuses(out) == ["unmatched_bank", "unmatched_ledger"]


def test_duplicate_entry_is_flagged():
    bank = [t(1, "INV-1", 100), t(2, "INV-1", 100)]
    out = reconcile(bank, [t(10, "INV-1", 100)])
    assert statuses(out) == ["duplicate", "matched"]


def test_two_identical_payments_on_both_sides_are_not_duplicates():
    bank = [t(1, "INV-1", 100), t(2, "INV-1", 100)]
    ledger = [t(10, "INV-1", 100), t(11, "INV-1", 100)]
    assert statuses(reconcile(bank, ledger)) == ["matched", "matched"]


def test_possible_match_without_reference():
    out = reconcile([t(1, "BANK-REF-9", 750)], [t(10, "INV-77", 750)])
    assert statuses(out) == ["possible_match"]
    assert out[0].confidence < 50


def test_empty_inputs():
    assert reconcile([], []) == []


def test_every_record_appears_exactly_once():
    bank = [t(1, "A", 100), t(2, "B", 200), t(3, "B", 200), t(4, "C", 50)]
    ledger = [t(10, "A", 100), t(11, "B", 250), t(12, "Z", 9)]
    out = reconcile(bank, ledger)
    assert sorted(o.bank_id for o in out if o.bank_id) == [1, 2, 3, 4]
    assert sorted(o.ledger_id for o in out if o.ledger_id) == [10, 11, 12]