from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsAdministrator
from .serializers import UserCreateSerializer, UserSerializer, UserUpdateSerializer

User = get_user_model()


class MeView(APIView):
    def get(self, request):
        return Response(
            {
                "username": request.user.username,
                "roles": list(request.user.groups.values_list("name", flat=True)),
                "is_superuser": request.user.is_superuser,
            }
        )


class UserListCreateView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        users = User.objects.prefetch_related("groups").order_by("username")
        return Response(UserSerializer(users, many=True).data)

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    permission_classes = [IsAdministrator]

    def patch(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target.is_superuser:
            return Response(
                {"detail": "Superusers are managed in the Django admin."}, status=status.HTTP_400_BAD_REQUEST
            )
        if target.pk == request.user.pk:
            return Response(
                {"detail": "You can't change your own role or access."}, status=status.HTTP_400_BAD_REQUEST
            )
        # partial=True: a missing field means "leave it alone" (form posts would otherwise turn a missing boolean into False)
        serializer = UserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            if "role" in data:
                target.groups.set([Group.objects.get(name=data["role"])])
            if "is_active" in data:
                target.is_active = data["is_active"]
                target.save(update_fields=["is_active"])
        target = User.objects.prefetch_related("groups").get(pk=target.pk)
        return Response(UserSerializer(target).data)