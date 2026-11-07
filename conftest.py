import pytest

BANK_CSV = (
    "reference,date,amount,description\n"
    "INV-1001,2026-10-01,50000.00,Alpha\n"
    "INV-1002,2026-10-02,12000.50,Beta\n"
    "INV-1003,2026-10-03,7500,Rent\n"
)
LEDGER_CSV = (
    "reference,date,amount,description\n"
    "INV-1001,2026-10-01,51500.00,Alpha\n"
    "INV-1002,2026-10-04,12000.50,Beta\n"
    "INV-1003,2026-10-03,7500,Rent\n"
    "INV-1006,2026-10-09,3200,Stationery\n"
)
PASSWORD = "pw-for-tests-123"


def _make_user(username, role):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    user = get_user_model().objects.create_user(username=username, password=PASSWORD)
    user.groups.add(Group.objects.get(name=role))
    return user


@pytest.fixture
def administrator(db):
    return _make_user("administrator_t", "Administrator")


@pytest.fixture
def analyst(db):
    return _make_user("analyst_t", "Analyst")


@pytest.fixture
def reviewer(db):
    return _make_user("reviewer_t", "Reviewer")


@pytest.fixture
def client_for():
    from rest_framework.test import APIClient

    def make(user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    return make


@pytest.fixture
def batches(analyst):
    from imports.services import import_file

    bank = import_file(content=BANK_CSV.encode(), filename="bank.csv", kind="bank", user=analyst)
    ledger = import_file(content=LEDGER_CSV.encode(), filename="ledger.csv", kind="ledger", user=analyst)
    return bank, ledger


@pytest.fixture
def run(batches, analyst):
    from reconciliation.services import run_reconciliation

    bank, ledger = batches
    return run_reconciliation(bank_batch_id=bank.id, ledger_batch_id=ledger.id, user=analyst)