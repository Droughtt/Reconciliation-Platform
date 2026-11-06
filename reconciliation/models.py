from django.conf import settings
from django.db import models
from imports.models import BankTransaction, ImportBatch, LedgerEntry

class ReconciliationRun(models.Model):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    bank_batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="+")
    ledger_batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

class MatchResult(models.Model):
    class Status(models.TextChoices):
        MATCHED = "matched", "Matched"
        AMOUNT_MISMATCH = "amount_mismatch", "Amount mismatch"
        DATE_MISMATCH = "date_mismatch", "Possible date mismatch"
        POSSIBLE_MATCH = "possible_match", "Possible match (low confidence)"
        UNMATCHED_BANK = "unmatched_bank", "In bank only"
        UNMATCHED_LEDGER = "unmatched_ledger", "In ledger only"
        DUPLICATE = "duplicate", "Duplicate entry"
        
    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="results")
    bank_txn = models.ForeignKey(BankTransaction, null=True, blank=True, on_delete=models.CASCADE)
    ledger_entry = models.ForeignKey(LedgerEntry, null=True, blank=True, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    confidence = models.PositiveSmallIntegerField(default=0)
    amount_difference = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    reason = models.CharField(max_length=255)

class Flag(models.Model):
    class Status(models.TextChoices):
        NEEDS_REVIEW = "needs_review", "Needs review"
        EXPLAINED = "explained", "Explained"
        DISMISSED = "dismissed", "Dismissed"
        ESCALATED = "escalated", "Escalated"
        
    result = models.OneToOneField(MatchResult, on_delete=models.CASCADE, related_name="flag")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEEDS_REVIEW)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)