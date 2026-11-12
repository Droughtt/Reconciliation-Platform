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
        # When the queryset is annotated (list view) use the pre-computed
        # counts to avoid N+1 queries.  Fall back to the per-run query for
        # single-object responses (e.g. after creating a run).
        from .models import MatchResult

        summary = {}
        for value, _ in MatchResult.Status.choices:
            attr = f"count_{value}"
            count = getattr(run, attr, None)
            if count is not None:
                if count > 0:
                    summary[value] = count
            else:
                # Not annotated — fallback to original per-run query.
                rows = run.results.values("status").annotate(n=Count("id"))
                return {row["status"]: row["n"] for row in rows}
        return summary


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