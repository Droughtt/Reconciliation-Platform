from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanReviewFlags, ReadOnlyAnyRole

from .flag_serializers import FlagDetailSerializer, FlagSerializer, FlagUpdateSerializer
from .models import Flag
from .review import FlagUpdateError, update_flag


class FlagListView(APIView):
    permission_classes = [ReadOnlyAnyRole]

    def get(self, request):
        flags = Flag.objects.select_related(
            "result__bank_txn", "result__ledger_entry", "reviewed_by"
        ).order_by("-updated_at")
        wanted = request.query_params.get("status")
        if wanted:
            flags = flags.filter(status=wanted)
        run_id = request.query_params.get("run")
        if run_id:
            flags = flags.filter(result__run_id=run_id)
        return Response(FlagSerializer(flags, many=True).data)


class FlagDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "PATCH":
            return [CanReviewFlags()]
        return [ReadOnlyAnyRole()]

    def get(self, request, pk):
        flag = get_object_or_404(
            Flag.objects.select_related("result__bank_txn", "result__ledger_entry", "reviewed_by")
            .prefetch_related("events__changed_by"),
            pk=pk,
        )
        return Response(FlagDetailSerializer(flag).data)

    def patch(self, request, pk):
        get_object_or_404(Flag, pk=pk)
        serializer = FlagUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            flag = update_flag(
                flag_id=pk,
                user=request.user,
                new_status=serializer.validated_data["status"],
                notes=serializer.validated_data.get("notes", ""),
            )
        except FlagUpdateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FlagDetailSerializer(flag).data)