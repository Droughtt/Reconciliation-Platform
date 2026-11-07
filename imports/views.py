from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanImportAndReconcile, ReadOnlyAnyRole

from .models import ImportBatch
from .serializers import ImportBatchDetailSerializer, ImportBatchSerializer, UploadSerializer
from .services import DuplicateUploadError, ImportFileError, import_file


class ImportBatchListCreateView(APIView):
    parser_classes = [MultiPartParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [CanImportAndReconcile()]
        return [ReadOnlyAnyRole()]

    def get(self, request):
        batches = ImportBatch.objects.select_related("uploaded_by")
        return Response(ImportBatchSerializer(batches, many=True).data)

    def post(self, request):
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        try:
            batch = import_file(
                content=upload.read(),
                filename=upload.name,
                kind=serializer.validated_data["kind"],
                user=request.user,
            )
        except ImportFileError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DuplicateUploadError as exc:
            body = {"detail": str(exc)}
            if exc.existing_batch:
                body["existing_batch_id"] = exc.existing_batch.id
            return Response(body, status=status.HTTP_409_CONFLICT)
        return Response(ImportBatchDetailSerializer(batch).data, status=status.HTTP_201_CREATED)


class ImportBatchDetailView(RetrieveAPIView):
    permission_classes = [ReadOnlyAnyRole]
    serializer_class = ImportBatchDetailSerializer
    queryset = ImportBatch.objects.select_related("uploaded_by").prefetch_related("row_errors")