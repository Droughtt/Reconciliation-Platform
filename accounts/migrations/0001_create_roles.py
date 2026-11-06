from django.db import migrations

ROLES = ["Administrator", "Analyst", "Reviewer"]


def create_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ROLES:
        Group.objects.get_or_create(name=name)


def remove_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [("auth", "__latest__")]
    operations = [migrations.RunPython(create_roles, remove_roles)]