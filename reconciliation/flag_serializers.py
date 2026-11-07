from rest_framework import serializers

from .models import Flag, FlagEvent
from .serializers import MatchResultSerializer


class FlagEventSerializer(serializers.ModelSerializer):
    changed_by = serializers.StringRelatedField()

    class Meta:
        model = FlagEvent
        fields = ["changed_by", "old_status", "new_status", "notes", "created_at"]


class FlagSerializer(serializers.ModelSerializer):
    reviewed_by = serializers.StringRelatedField()
    result = MatchResultSerializer(read_only=True)

    class Meta:
        model = Flag
        fields = ["id", "status", "notes", "reviewed_by", "updated_at", "result"]


class FlagDetailSerializer(FlagSerializer):
    events = FlagEventSerializer(many=True, read_only=True)

    class Meta(FlagSerializer.Meta):
        fields = FlagSerializer.Meta.fields + ["events"]


class FlagUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Flag.Status.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)