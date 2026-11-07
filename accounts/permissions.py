from rest_framework.permissions import SAFE_METHODS, BasePermission

ADMIN = "Administrator"
ANALYST = "Analyst"
REVIEWER = "Reviewer"


def has_role(user, *roles):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=roles).exists()


class IsAdministrator(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, ADMIN)


class CanImportAndReconcile(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, ADMIN, ANALYST)


class CanReviewFlags(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, ADMIN, REVIEWER)


class ReadOnlyAnyRole(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS and has_role(
            request.user, ADMIN, ANALYST, REVIEWER
        )