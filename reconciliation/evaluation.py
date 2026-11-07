import argparse
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from reconciliation.engine import Txn, reconcile

LABELS = [
    "clean", "amount_mismatch", "date_mismatch", "missing_in_ledger",
    "missing_in_bank", "duplicate_in_bank", "reference_typo",
]
WEIGHTS = [70, 6, 6, 5, 5, 4, 4]

# What the engine should say about each kind of injected error
EXPECTED_STATUSES = {
    "clean": {"matched"},
    "amount_mismatch": {"amount_mismatch"},
    "date_mismatch": {"date_mismatch"},
    "missing_in_ledger": {"unmatched_bank"},
    "missing_in_bank": {"unmatched_ledger"},
    "duplicate_in_bank": {"matched", "duplicate"},
    "reference_typo": {"possible_match"},
}
PREDICTED_LABEL = {frozenset(v): k for k, v in EXPECTED_STATUSES.items()}


@dataclass
class Dataset:
    bank: list
    ledger: list
    truth: dict          # base transaction number -> injected label
    bank_base: dict      # bank record id -> base transaction number
    ledger_base: dict    # ledger record id -> base transaction number


def _money(cents):
    return Decimal(cents).scaleb(-2)


def generate(n=500, seed=42, amount_pool=0):
    """Make n base transactions and inject known errors. amount_pool > 0 draws
    amounts from a small pool, which creates look-alike amounts (a harder test)."""
    rng = random.Random(seed)
    pool = [_money(rng.randint(100000, 10000000)) for _ in range(amount_pool)]
    start = date(2026, 1, 1)
    bank, ledger, truth = [], [], {}
    bank_base, ledger_base = {}, {}

    def add(records, owner, base, ref, d, amount):
        rid = len(records) + 1
        records.append(Txn(id=rid, reference=ref, txn_date=d, amount=amount))
        owner[rid] = base

    for i in range(n):
        label = rng.choices(LABELS, weights=WEIGHTS)[0]
        truth[i] = label
        ref = f"INV-{i:05d}"
        d = start + timedelta(days=rng.randint(0, 180))
        amount = rng.choice(pool) if pool else _money(rng.randint(100000, 10000000))

        bank_ref, bank_date, bank_amount = ref, d, amount
        ledger_ref = ref

        if label == "amount_mismatch":
            delta = _money(rng.randint(1, 50000))
            bank_amount = amount + delta if rng.random() < 0.5 else amount - delta
        elif label == "date_mismatch":
            bank_date = d + timedelta(days=rng.randint(1, 5))
        elif label == "reference_typo":
            ledger_ref = "INX" + ref[3:]

        if label != "missing_in_bank":
            add(bank, bank_base, i, bank_ref, bank_date, bank_amount)
            if label == "duplicate_in_bank":
                add(bank, bank_base, i, bank_ref, bank_date, bank_amount)
        if label != "missing_in_ledger":
            add(ledger, ledger_base, i, ledger_ref, d, amount)

    return Dataset(bank, ledger, truth, bank_base, ledger_base)


def evaluate(outcomes, data):
    """Turn engine outcomes into one predicted label per base transaction."""
    statuses = defaultdict(set)
    mis_paired = set()
    for o in outcomes:
        b = data.bank_base.get(o.bank_id) if o.bank_id is not None else None
        l = data.ledger_base.get(o.ledger_id) if o.ledger_id is not None else None
        if b is not None and l is not None and b != l:
            mis_paired.update({b, l})  # engine paired two unrelated records
        for base in (b, l):
            if base is not None:
                statuses[base].add(o.status)
    predicted = {}
    for base in data.truth:
        if base in mis_paired:
            predicted[base] = "mis_paired"
        else:
            predicted[base] = PREDICTED_LABEL.get(frozenset(statuses[base]), "other")
    return predicted


def accuracy(truth, predicted):
    return sum(1 for b in truth if truth[b] == predicted[b]) / len(truth)


def format_report(truth, predicted, seed, window, amount_pool):
    total = len(truth)
    correct = sum(1 for b in truth if truth[b] == predicted[b])
    lines = [
        f"Synthetic evaluation: {total} base transactions, seed={seed}, "
        f"date window={window} days, amount pool={amount_pool or 'off'}",
        f"Overall: {correct}/{total} classified correctly ({correct / total:.1%})",
        "",
        f"{'label':<20}{'count':>7}{'precision':>11}{'recall':>9}",
    ]
    for label in LABELS:
        actual = sum(1 for b in truth if truth[b] == label)
        tp = sum(1 for b in truth if truth[b] == label and predicted[b] == label)
        fp = sum(1 for b in truth if predicted[b] == label and truth[b] != label)
        precision = f"{tp / (tp + fp):.1%}" if tp + fp else "n/a"
        recall = f"{tp / actual:.1%}" if actual else "n/a"
        lines.append(f"{label:<20}{actual:>7}{precision:>11}{recall:>9}")
    mis = sum(1 for b in truth if predicted[b] == "mis_paired")
    lines.append(f"{'mis_paired':<20}{mis:>7}")
    wrong = [b for b in truth if truth[b] != predicted[b]]
    if wrong:
        lines += ["", f"Misclassified ({len(wrong)}), first 10:"]
        for b in wrong[:10]:
            lines.append(f"  INV-{b:05d}: expected {truth[b]}, got {predicted[b]}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Score the matching engine on synthetic data.")
    parser.add_argument("--n", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--amount-pool", type=int, default=0)
    args = parser.parse_args()

    data = generate(args.n, args.seed, args.amount_pool)
    outcomes = reconcile(data.bank, data.ledger, args.window)
    predicted = evaluate(outcomes, data)
    print(format_report(data.truth, predicted, args.seed, args.window, args.amount_pool))


if __name__ == "__main__":
    main()