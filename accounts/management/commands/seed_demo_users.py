from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

DEMO_USERS = [
    ("admin_demo", "Administrator"),
    ("analyst_demo", "Analyst"),
    ("reviewer_demo", "Reviewer"),
]


class Command(BaseCommand):
    help = "Create one demo user per role (demo data only)."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True)

    def handle(self, *args, **opts):
        User = get_user_model()
        for username, role in DEMO_USERS:
            user, created = User.objects.get_or_create(username=username)
            user.set_password(opts["password"])
            user.save()
            user.groups.set([Group.objects.get(name=role)])
            self.stdout.write(f"{'created' if created else 'updated'} {username} ({role})")