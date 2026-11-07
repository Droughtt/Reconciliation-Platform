from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanImportAndReconcile, ReadOnlyAnyRole

from .models import ReconciliationRun
from .serializers import MatchResultSerializer, RunRequestSerializer, RunSerializer
from .services import RunInputError, run_reconciliation


class RunListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [CanImportAndReconcile()]
        return [ReadOnlyAnyRole()]

    def get(self, request):
        runs = ReconciliationRun.objects.select_related("created_by").order_by("-created_at")
        return Response(RunSerializer(runs, many=True).data)

    def post(self, request):
        serializer = RunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = run_reconciliation(user=request.user, **serializer.validated_data)
        except RunInputError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RunSerializer(run).data, status=status.HTTP_201_CREATED)


class RunDetailView(APIView):
    permission_classes = [ReadOnlyAnyRole]

    def get(self, request, pk):
        run = get_object_or_404(ReconciliationRun, pk=pk)
        results = run.results.select_related("bank_txn", "ledger_entry", "flag")
        wanted = request.query_params.get("status")
        if wanted:
            results = results.filter(status=wanted)
        return Response(
            {
                "run": RunSerializer(run).data,
                "results": MatchResultSerializer(results, many=True).data,
            }
        )