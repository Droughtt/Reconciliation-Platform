from django.conf import settings
from django.db import models

class ImportBatch(models.Model):
    class Kind(models.TextChoices):
        BANK = "bank", "Bank statement"
        LEDGER = "ledger", "Company ledger"
        
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        
    kind = models.CharField(max_length=10, choices=Kind.choices)
    original_filename = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="import_batches"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING)
    total_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "file_hash"], name="uniq_batch_kind_filehash")
        ]
        
    def __str__(self):
        return f"{self.kind}: {self.original_filename}"

class RowError(models.Model):
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="row_errors")
    row_number = models.PositiveIntegerField()
    raw_data = models.JSONField()
    reason = models.CharField(max_length=255)

class BaseRecord(models.Model):
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="%(class)ss")
    row_number = models.PositiveIntegerField()
    reference = models.CharField(max_length=100)
    txn_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    
    class Meta:
        abstract = True

class BankTransaction(BaseRecord):
    class Meta:
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["txn_date", "amount"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_number"], name="uniq_bank_batch_row")
        ]

class LedgerEntry(BaseRecord):
    class Meta:
        indexes = [
            models.Index(fields=["reference"]),
            models.Index(fields=["txn_date", "amount"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_number"], name="uniq_ledger_batch_row")
        ]
