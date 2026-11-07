from django.contrib import admin

from .models import BankTransaction, ImportBatch, LedgerEntry, RowError

admin.site.register(ImportBatch)
admin.site.register(BankTransaction)
admin.site.register(LedgerEntry)
admin.site.register(RowError)