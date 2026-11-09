import csv
import hashlib
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction

from .models import BankTransaction, ImportBatch, LedgerEntry, RowError

REQUIRED_COLUMNS = {"reference", "date", "amount"}
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")
MAX_BYTES = 5 * 1024 * 1024
MAX_AMOUNT = Decimal("999999999999.99")


class ImportFileError(Exception):
    """The whole file is unusable (bad encoding, missing columns, empty)."""


class DuplicateUploadError(Exception):
    """This exact file was already imported."""

    def __init__(self, existing_batch=None):
        self.existing_batch = existing_batch
        super().__init__("This file has already been imported.")


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_date(raw: str):
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        raise ValueError(f"date '{raw}' is not a real date (use YYYY-MM-DD, DD-MM-YYYY or DD/MM/YYYY)")


def parse_amount(raw: str) -> Decimal:
    cleaned = raw.replace("₹", "").replace(",", "").strip()
    if not cleaned:
        raise ValueError("amount is empty")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"amount '{raw}' is not a number")
    if not value.is_finite():
        raise ValueError(f"amount '{raw}' is not a number")
    if value <= 0:
        raise ValueError("amount must be greater than zero")
    if value > MAX_AMOUNT:
        raise ValueError("amount is too large")
    if value != value.quantize(Decimal("0.01")):
        raise ValueError("amount has more than 2 decimal places")
    return value.quantize(Decimal("0.01"))
    

def validate_row(row: dict) -> dict:
    reference = (row.get("reference") or "").strip().upper()
    if not reference:
        raise ValueError("reference is missing")
    if len(reference) > 100:
        raise ValueError("reference is longer than 100 characters")
    return {
        "reference": reference,
        "txn_date": parse_date(row.get("date") or ""),
        "amount": parse_amount(row.get("amount") or ""),
        "description": (row.get("description") or "").strip()[:255],
    }


def import_file(*, content: bytes, filename: str, kind: str, user) -> ImportBatch:
    if not content:
        raise ImportFileError("File is empty.")
    if len(content) > MAX_BYTES:
        raise ImportFileError("File is larger than 5 MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFileError("File must be UTF-8 encoded CSV.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportFileError("File has no header row.")
    reader.fieldnames = [(h or "").strip().lower() for h in reader.fieldnames]
    missing = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing:
        raise ImportFileError(f"Missing required columns: {', '.join(sorted(missing))}")

    digest = file_sha256(content)
    existing = ImportBatch.objects.filter(kind=kind, file_hash=digest).first()
    if existing:
        raise DuplicateUploadError(existing)

    model = BankTransaction if kind == ImportBatch.Kind.BANK else LedgerEntry

    try:
        with transaction.atomic():
            batch = ImportBatch.objects.create(
                kind=kind, original_filename=filename[:255], file_hash=digest, uploaded_by=user
            )
            records, errors, total = [], [], 0
            for row in reader:
                total += 1
                row_number = reader.line_num
                try:
                    clean = validate_row(row)
                except ValueError as exc:
                    raw = {str(k): v for k, v in row.items()}
                    errors.append(
                        RowError(batch=batch, row_number=row_number, raw_data=raw, reason=str(exc))
                    )
                else:
                    records.append(model(batch=batch, row_number=row_number, **clean))

            if total == 0:
                raise ImportFileError("File has a header but no data rows.")

            model.objects.bulk_create(records, batch_size=1000)
            RowError.objects.bulk_create(errors, batch_size=1000)
            batch.total_rows = total
            batch.imported_rows = len(records)
            batch.failed_rows = len(errors)
            batch.status = ImportBatch.Status.COMPLETED if records else ImportBatch.Status.FAILED
            batch.save()
    except IntegrityError:
        # two identical uploads raced; the unique constraint caught the loser
        raise DuplicateUploadError()
    return batch