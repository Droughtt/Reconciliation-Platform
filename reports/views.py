from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import ReadOnlyAnyRole
from reconciliation.models import ReconciliationRun

from .services import build_summary, write_results_csv


def _get_run(pk):
    return get_object_or_404(
        ReconciliationRun.objects.select_related("bank_batch", "ledger_batch", "created_by"),
        pk=pk,
    )


class RunSummaryView(APIView):
    permission_classes = [ReadOnlyAnyRole]

    def get(self, request, pk):
        return Response(build_summary(_get_run(pk)))


class RunExportView(APIView):
    permission_classes = [ReadOnlyAnyRole]

    def get(self, request, pk):
        run = _get_run(pk)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="reconciliation_run_{run.id}.csv"'
        response.write("\ufeff")  # BOM so Excel shows the rupee sign correctly
        write_results_csv(run, response, status=request.query_params.get("status"))
        return response