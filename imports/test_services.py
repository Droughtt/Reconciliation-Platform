from datetime import date
from decimal import Decimal

import pytest

from imports.models import BankTransaction, ImportBatch, RowError
from imports.services import (
    MAX_BYTES, DuplicateUploadError, ImportFileError,
    import_file, parse_amount, parse_date, validate_row,
)

GOOD = "reference,date,amount,description\nINV-1,2026-10-01,100,a\nINV-2,2026-10-02,200,b\n"
MIXED = GOOD + "INV-3,31/02/2026,10,bad date\nINV-4,2026-10-05,abc,bad amount\n,2026-10-06,5,no ref\n"


def do_import(content, user, kind="bank"):
    if isinstance(content, str):
        content = content.encode()
    return import_file(content=content, filename="f.csv", kind=kind, user=user)


@pytest.mark.parametrize("raw,expected", [
    ("100", "100.00"), ("12,000.50", "12000.50"), ("₹1,200.5", "1200.50"), (" 7500 ", "7500.00"),
])
def test_parse_amount_valid(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", [
    "", "abc", "0", "-5", "10.005", "NaN", "Infinity",
    "1e30", "99999999999999999999999999999",
])
def test_parse_amount_invalid(raw):
    with pytest.raises(ValueError):
        parse_amount(raw)


def test_parse_date_accepts_three_formats():
    assert parse_date("2026-10-01") == date(2026, 10, 1)
    assert parse_date("01-10-2026") == date(2026, 10, 1)
    assert parse_date("01/10/2026") == date(2026, 10, 1)


@pytest.mark.parametrize("raw", ["", "31/02/2026", "2026-13-01", "yesterday"])
def test_parse_date_invalid(raw):
    with pytest.raises(ValueError):
        parse_date(raw)


def test_validate_row_cleans_values():
    row = validate_row({"reference": "  inv-1 ", "date": "2026-10-01", "amount": "5", "description": " x "})
    assert row["reference"] == "INV-1"
    assert row["description"] == "x"
    assert row["amount"] == Decimal("5.00")


@pytest.mark.parametrize("row", [
    {"reference": "", "date": "2026-10-01", "amount": "5"},
    {"reference": None, "date": "2026-10-01", "amount": "5"},
    {"reference": "A" * 101, "date": "2026-10-01", "amount": "5"},
    {"reference": "A", "date": None, "amount": "5"},
    {"reference": "A", "date": "2026-10-01", "amount": None},
])
def test_validate_row_rejects_bad_rows(row):
    with pytest.raises(ValueError):
        validate_row(row)


def test_import_good_file(analyst):
    batch = do_import(GOOD, analyst)
    assert (batch.total_rows, batch.imported_rows, batch.failed_rows) == (2, 2, 0)
    assert batch.status == ImportBatch.Status.COMPLETED
    assert BankTransaction.objects.filter(batch=batch).count() == 2


def test_import_reports_bad_rows_with_file_line_numbers(analyst):
    batch = do_import(MIXED, analyst)
    assert (batch.total_rows, batch.imported_rows, batch.failed_rows) == (5, 2, 3)
    errors = RowError.objects.filter(batch=batch).order_by("row_number")
    assert [e.row_number for e in errors] == [4, 5, 6]
    assert all(e.reason for e in errors)


def test_file_with_only_bad_rows_is_marked_failed(analyst):
    batch = do_import("reference,date,amount\n,x,y\n", analyst)
    assert batch.status == ImportBatch.Status.FAILED
    assert batch.imported_rows == 0


def test_duplicate_upload_is_rejected(analyst):
    do_import(GOOD, analyst)
    with pytest.raises(DuplicateUploadError):
        do_import(GOOD, analyst)
    assert ImportBatch.objects.count() == 1


def test_same_file_can_be_uploaded_as_other_kind(analyst):
    do_import(GOOD, analyst, kind="bank")
    do_import(GOOD, analyst, kind="ledger")
    assert ImportBatch.objects.count() == 2


def test_header_is_case_insensitive_and_bom_is_ignored(analyst):
    batch = do_import("\ufeffReference,DATE,Amount\nINV-1,2026-10-01,5\n", analyst)
    assert batch.imported_rows == 1


@pytest.mark.parametrize("content", [
    b"",
    b"reference,date\nA,2026-10-01\n",
    b"reference,date,amount\n",
    b"\xff\xfe\x00not utf8",
    b"a" * (MAX_BYTES + 1),
], ids=["empty", "missing-column", "header-only", "not-utf8", "too-big"])
def test_unusable_files_are_rejected_and_leave_nothing_behind(analyst, content):
    with pytest.raises(ImportFileError):
        do_import(content, analyst)
    assert ImportBatch.objects.count() == 0