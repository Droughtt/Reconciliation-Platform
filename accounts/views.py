from rest_framework.response import Response
from rest_framework.views import APIView


class MeView(APIView):
    def get(self, request):
        return Response(
            {
                "username": request.user.username,
                "roles": list(request.user.groups.values_list("name", flat=True)),
                "is_superuser": request.user.is_superuser,
            }
        )