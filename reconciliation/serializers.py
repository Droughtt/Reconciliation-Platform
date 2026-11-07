from django.db.models import Count
from rest_framework import serializers

from .models import MatchResult, ReconciliationRun


class RunRequestSerializer(serializers.Serializer):
    bank_batch_id = serializers.IntegerField()
    ledger_batch_id = serializers.IntegerField()


class RunSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = ReconciliationRun
        fields = ["id", "bank_batch", "ledger_batch", "created_by", "created_at", "summary"]

    def get_summary(self, run):
        rows = run.results.values("status").annotate(n=Count("id"))
        return {row["status"]: row["n"] for row in rows}


def _side(record):
    if record is None:
        return None
    return {
        "id": record.id,
        "reference": record.reference,
        "date": record.txn_date,
        "amount": str(record.amount),
    }


class MatchResultSerializer(serializers.ModelSerializer):
    bank = serializers.SerializerMethodField()
    ledger = serializers.SerializerMethodField()
    flag_status = serializers.SerializerMethodField()

    class Meta:
        model = MatchResult
        fields = [
            "id", "status", "confidence", "amount_difference", "reason",
            "bank", "ledger", "flag_status",
        ]

    def get_bank(self, obj):
        return _side(obj.bank_txn)

    def get_ledger(self, obj):
        return _side(obj.ledger_entry)

    def get_flag_status(self, obj):
        flag = getattr(obj, "flag", None)
        return flag.status if flag else None