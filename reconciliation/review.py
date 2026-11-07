from django.db import transaction

from .models import Flag, FlagEvent

NOTE_REQUIRED = {Flag.Status.DISMISSED, Flag.Status.ESCALATED}


class FlagUpdateError(Exception):
    """The requested flag change is not allowed."""


def update_flag(*, flag_id, user, new_status, notes=""):
    notes = (notes or "").strip()
    with transaction.atomic():
        flag = Flag.objects.select_for_update().get(pk=flag_id)
        if new_status == flag.status:
            raise FlagUpdateError(f"Flag is already '{flag.status}'.")
        if new_status in NOTE_REQUIRED and not notes:
            raise FlagUpdateError("A note is required when dismissing or escalating a flag.")
        FlagEvent.objects.create(
            flag=flag,
            changed_by=user,
            old_status=flag.status,
            new_status=new_status,
            notes=notes,
        )
        flag.status = new_status
        if notes:
            flag.notes = notes
        flag.reviewed_by = user
        flag.save()
    return flag