from reconciliation.engine import reconcile
from reconciliation.evaluation import LABELS, accuracy, evaluate, generate


def test_generator_is_reproducible():
    a, b = generate(100, seed=1), generate(100, seed=1)
    assert a.bank == b.bank and a.ledger == b.ledger and a.truth == b.truth


def test_generator_injects_every_error_type():
    assert set(generate(1000, seed=7).truth.values()) == set(LABELS)


def test_every_generated_record_is_accounted_for():
    data = generate(300, seed=3)
    out = reconcile(data.bank, data.ledger)
    assert sorted(o.bank_id for o in out if o.bank_id is not None) == sorted(t.id for t in data.bank)
    assert sorted(o.ledger_id for o in out if o.ledger_id is not None) == sorted(t.id for t in data.ledger)


def test_engine_recovers_injected_errors():
    data = generate(500, seed=42)
    predicted = evaluate(reconcile(data.bank, data.ledger), data)
    assert accuracy(data.truth, predicted) >= 0.98