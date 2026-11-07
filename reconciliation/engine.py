from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Txn:
    id: int
    reference: str
    txn_date: date
    amount: Decimal


@dataclass
class Outcome:
    status: str
    bank_id: int | None
    ledger_id: int | None
    confidence: int
    amount_difference: Decimal | None
    reason: str


def _key(t: Txn):
    return (t.reference, t.txn_date, t.amount)


def _days_apart(a: Txn, b: Txn) -> int:
    return abs((a.txn_date - b.txn_date).days)


def _pair(bank_left, ledger_left, outcomes, matches, build):
    """Pair each bank record with the first ledger record that satisfies
    `matches`. Each record is used at most once. Returns what is left."""
    ledger_left = list(ledger_left)
    bank_remaining = []
    for b in bank_left:
        hit = next((l for l in ledger_left if matches(b, l)), None)
        if hit is None:
            bank_remaining.append(b)
        else:
            ledger_left.remove(hit)
            outcomes.append(build(b, hit))
    return bank_remaining, ledger_left

def _pass_exact(bank, ledger, outcomes):
    index = defaultdict(list)
    for l in ledger:
        index[_key(l)].append(l)

    matched_keys = set()
    bank_left = []
    for b in bank:
        candidates = index[_key(b)]
        if candidates:
            l = candidates.pop()
            outcomes.append(
                Outcome("matched", b.id, l.id, 100, None,
                        "Reference, date and amount all match")
            )
            matched_keys.add(_key(b))
        else:
            bank_left.append(b)

    ledger_left = [l for group in index.values() for l in group]
    return bank_left, ledger_left, matched_keys


def _pass_duplicates(bank_left, ledger_left, matched_keys, outcomes):
    bank_remaining, ledger_remaining = [], []
    for b in bank_left:
        if _key(b) in matched_keys:
            outcomes.append(
                Outcome("duplicate", b.id, None, 90, None,
                        "Identical to a bank record that was already matched; possible duplicate entry")
            )
        else:
            bank_remaining.append(b)
    for l in ledger_left:
        if _key(l) in matched_keys:
            outcomes.append(
                Outcome("duplicate", None, l.id, 90, None,
                        "Identical to a ledger entry that was already matched; possible duplicate entry")
            )
        else:
            ledger_remaining.append(l)
    return bank_remaining, ledger_remaining

def _pass_date_mismatch(bank_left, ledger_left, outcomes, window):
    def matches(b, l):
        return b.reference == l.reference and b.amount == l.amount and _days_apart(b, l) <= window

    def build(b, l):
        return Outcome("date_mismatch", b.id, l.id, 80, None,
                       f"Reference and amount match but dates differ by {_days_apart(b, l)} day(s)")

    return _pair(bank_left, ledger_left, outcomes, matches, build)


def _pass_amount_mismatch(bank_left, ledger_left, outcomes, window):
    def matches(b, l):
        return b.reference == l.reference and b.amount != l.amount and _days_apart(b, l) <= window

    def build(b, l):
        diff = b.amount - l.amount
        return Outcome("amount_mismatch", b.id, l.id, 70, diff,
                       f"Reference matches but bank amount differs from ledger by {diff} (bank minus ledger)")

    return _pair(bank_left, ledger_left, outcomes, matches, build)


def _pass_possible_match(bank_left, ledger_left, outcomes, window):
    def candidates(record, others):
        return [
            o for o in others
            if record.reference != o.reference
            and record.amount == o.amount
            and _days_apart(record, o) <= window
        ]

    paired_bank, paired_ledger = set(), set()
    for b in bank_left:
        options = candidates(b, ledger_left)
        # pair only when b and its single candidate pick each other and nobody else
        if len(options) == 1 and len(candidates(options[0], bank_left)) == 1:
            l = options[0]
            paired_bank.add(b.id)
            paired_ledger.add(l.id)
            outcomes.append(
                Outcome("possible_match", b.id, l.id, 40, None,
                        "Amount and date are close but references differ; needs human confirmation")
            )
    return (
        [b for b in bank_left if b.id not in paired_bank],
        [l for l in ledger_left if l.id not in paired_ledger],
    )
    def matches(b, l):
        return b.reference != l.reference and b.amount == l.amount and _days_apart(b, l) <= window

    def build(b, l):
        return Outcome("possible_match", b.id, l.id, 40, None,
                       "Amount and date are close but references differ; needs human confirmation")

    return _pair(bank_left, ledger_left, outcomes, matches, build)

def _pass_leftovers(bank_left, ledger_left, outcomes):
    for b in bank_left:
        outcomes.append(Outcome("unmatched_bank", b.id, None, 0, None, "Found in bank statement only"))
    for l in ledger_left:
        outcomes.append(Outcome("unmatched_ledger", None, l.id, 0, None, "Found in company ledger only"))


def reconcile(bank: list[Txn], ledger: list[Txn], date_window_days: int = 5) -> list[Outcome]:
    outcomes: list[Outcome] = []
    bank_left, ledger_left, matched_keys = _pass_exact(bank, ledger, outcomes)
    bank_left, ledger_left = _pass_duplicates(bank_left, ledger_left, matched_keys, outcomes)
    bank_left, ledger_left = _pass_date_mismatch(bank_left, ledger_left, outcomes, date_window_days)
    bank_left, ledger_left = _pass_amount_mismatch(bank_left, ledger_left, outcomes, date_window_days)
    bank_left, ledger_left = _pass_possible_match(bank_left, ledger_left, outcomes, date_window_days)
    _pass_leftovers(bank_left, ledger_left, outcomes)
    return outcomes