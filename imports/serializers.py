from rest_framework import serializers

from .models import ImportBatch, RowError


class UploadSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ImportBatch.Kind.choices)
    file = serializers.FileField()

    def validate_file(self, value):
        if not value.name.lower().endswith(".csv"):
            raise serializers.ValidationError("Only .csv files are accepted.")
        return value


class RowErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = RowError
        fields = ["row_number", "raw_data", "reason"]


class ImportBatchSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.StringRelatedField()

    class Meta:
        model = ImportBatch
        fields = [
            "id", "kind", "original_filename", "status", "total_rows",
            "imported_rows", "failed_rows", "uploaded_by", "created_at",
        ]


class ImportBatchDetailSerializer(ImportBatchSerializer):
    row_errors = RowErrorSerializer(many=True, read_only=True)

    class Meta(ImportBatchSerializer.Meta):
        fields = ImportBatchSerializer.Meta.fields + ["row_errors"]