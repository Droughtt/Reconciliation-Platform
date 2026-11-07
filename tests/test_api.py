import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from reconciliation.models import Flag, FlagEvent, MatchResult
from reports.services import _safe

GOOD = b"reference,date,amount\nINV-1,2026-10-01,100\nINV-2,2026-10-02,200\n"
MIXED = GOOD + b"INV-3,31/02/2026,10\nINV-4,2026-10-05,abc\n,2026-10-06,5\n"
FRESH = b"reference,date,amount\nUP-1,2026-10-01,10\n"


def user_for(request, role):
    return request.getfixturevalue(role) if role else None


def upload(client, content, name="x.csv", kind="bank"):
    f = SimpleUploadedFile(name, content, content_type="text/csv")
    return client.post(reverse("import-list"), {"kind": kind, "file": f}, format="multipart")


@pytest.fixture
def flag(run):
    return Flag.objects.get(result__status=MatchResult.Status.AMOUNT_MISMATCH)


@pytest.fixture
def urls(run, flag):
    return {
        "me": reverse("me"),
        "import-list": reverse("import-list"),
        "import-detail": reverse("import-detail", args=[run.bank_batch_id]),
        "run-list": reverse("run-list"),
        "run-detail": reverse("run-detail", args=[run.id]),
        "run-summary": reverse("run-summary", args=[run.id]),
        "run-export": reverse("run-export", args=[run.id]),
        "flag-list": reverse("flag-list"),
        "flag-detail": reverse("flag-detail", args=[flag.id]),
    }


# ---------- login ----------

def test_token_login_then_me(analyst):
    r = APIClient().post(reverse("token"), {"username": "analyst_t", "password": "pw-for-tests-123"}, format="json")
    assert r.status_code == 200
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {r.data['token']}")
    me = client.get(reverse("me"))
    assert me.status_code == 200 and me.data["roles"] == ["Analyst"]


def test_wrong_password_is_rejected(analyst):
    r = APIClient().post(reverse("token"), {"username": "analyst_t", "password": "nope"}, format="json")
    assert r.status_code == 400


def test_garbage_token_is_rejected(db):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
    assert client.get(reverse("me")).status_code == 401


# ---------- who can do what ----------

@pytest.mark.parametrize("role,expected", [("administrator", 200), ("analyst", 200), ("reviewer", 200), (None, 401)])
@pytest.mark.parametrize("name", [
    "me", "import-list", "import-detail", "run-list", "run-detail",
    "run-summary", "run-export", "flag-list", "flag-detail",
])
def test_read_access(request, client_for, urls, name, role, expected):
    resp = client_for(user_for(request, role)).get(urls[name])
    assert resp.status_code == expected


@pytest.mark.parametrize("role,expected", [("administrator", 201), ("analyst", 201), ("reviewer", 403), (None, 401)])
def test_upload_permissions(request, db, client_for, role, expected):
    assert upload(client_for(user_for(request, role)), FRESH).status_code == expected


@pytest.mark.parametrize("role,expected", [("administrator", 201), ("analyst", 201), ("reviewer", 403), (None, 401)])
def test_run_permissions(request, client_for, batches, role, expected):
    bank, ledger = batches
    body = {"bank_batch_id": bank.id, "ledger_batch_id": ledger.id}
    resp = client_for(user_for(request, role)).post(reverse("run-list"), body, format="json")
    assert resp.status_code == expected


@pytest.mark.parametrize("role,expected", [("administrator", 200), ("reviewer", 200), ("analyst", 403), (None, 401)])
def test_flag_update_permissions(request, client_for, urls, role, expected):
    resp = client_for(user_for(request, role)).patch(urls["flag-detail"], {"status": "explained"}, format="json")
    assert resp.status_code == expected


# ---------- uploads ----------

def test_upload_ok(client_for, analyst):
    r = upload(client_for(analyst), GOOD)
    assert r.status_code == 201 and r.data["imported_rows"] == 2


def test_upload_reports_failed_rows(client_for, analyst):
    r = upload(client_for(analyst), MIXED)
    assert r.status_code == 201
    assert r.data["failed_rows"] == 3 and len(r.data["row_errors"]) == 3


def test_duplicate_upload_is_409(client_for, analyst):
    client = client_for(analyst)
    first = upload(client, GOOD)
    second = upload(client, GOOD)
    assert second.status_code == 409
    assert second.data["existing_batch_id"] == first.data["id"]


def test_bad_uploads_are_400(client_for, analyst):
    client = client_for(analyst)
    assert upload(client, GOOD, name="x.txt").status_code == 400
    assert upload(client, b"foo,bar\n1,2\n").status_code == 400
    assert upload(client, GOOD, kind="nope").status_code == 400
    no_file = client.post(reverse("import-list"), {"kind": "bank"}, format="multipart")
    assert no_file.status_code == 400


# ---------- reconciliation runs ----------

def test_run_saves_results_and_flags(client_for, analyst, batches):
    bank, ledger = batches
    r = client_for(analyst).post(
        reverse("run-list"), {"bank_batch_id": bank.id, "ledger_batch_id": ledger.id}, format="json"
    )
    assert r.status_code == 201
    assert r.data["summary"] == {"matched": 1, "date_mismatch": 1, "amount_mismatch": 1, "unmatched_ledger": 1}
    assert Flag.objects.count() == 3


def test_run_rejects_bad_input(client_for, analyst, batches):
    bank, ledger = batches
    client = client_for(analyst)
    url = reverse("run-list")
    assert client.post(url, {"bank_batch_id": 99999, "ledger_batch_id": ledger.id}, format="json").status_code == 400
    assert client.post(url, {"bank_batch_id": ledger.id, "ledger_batch_id": bank.id}, format="json").status_code == 400
    assert client.post(url, {}, format="json").status_code == 400
    failed = upload(client, b"reference,date,amount\n,x,y\n").data["id"]
    assert client.post(url, {"bank_batch_id": failed, "ledger_batch_id": ledger.id}, format="json").status_code == 400


def test_matched_results_get_no_flag(run):
    assert not Flag.objects.filter(result__status=MatchResult.Status.MATCHED).exists()


def test_no_status_is_ever_called_fraud():
    for value in list(Flag.Status.values) + list(MatchResult.Status.values):
        assert "fraud" not in value.lower()


# ---------- flag review ----------

def test_dismiss_needs_a_note(client_for, reviewer, flag):
    r = client_for(reviewer).patch(reverse("flag-detail", args=[flag.id]), {"status": "dismissed"}, format="json")
    assert r.status_code == 400
    flag.refresh_from_db()
    assert flag.status == "needs_review" and FlagEvent.objects.count() == 0


def test_dismiss_with_note_is_audited(client_for, reviewer, flag):
    body = {"status": "dismissed", "notes": "Timing difference"}
    r = client_for(reviewer).patch(reverse("flag-detail", args=[flag.id]), body, format="json")
    assert r.status_code == 200
    flag.refresh_from_db()
    assert flag.status == "dismissed" and flag.reviewed_by == reviewer
    event = FlagEvent.objects.get()
    assert (event.old_status, event.new_status, event.changed_by) == ("needs_review", "dismissed", reviewer)


def test_repeating_a_status_or_using_a_bad_one_is_rejected(client_for, reviewer, flag):
    client = client_for(reviewer)
    url = reverse("flag-detail", args=[flag.id])
    assert client.patch(url, {"status": "explained"}, format="json").status_code == 200
    assert client.patch(url, {"status": "explained"}, format="json").status_code == 400
    assert client.patch(url, {"status": "fraud"}, format="json").status_code == 400


def test_missing_flag_is_404(client_for, reviewer, db):
    r = client_for(reviewer).patch(reverse("flag-detail", args=[99999]), {"status": "explained"}, format="json")
    assert r.status_code == 404


# ---------- reports ----------

def test_summary_numbers(client_for, reviewer, run):
    data = client_for(reviewer).get(reverse("run-summary", args=[run.id])).data
    assert data["totals"]["bank_total"] == "69500.50"
    assert data["totals"]["ledger_total"] == "74200.50"
    assert data["totals"]["net_difference"] == "-4700.00"
    assert data["totals"]["amount_mismatch_net"] == "-1500.00"
    assert data["open_flags"] == 3


def test_csv_export(client_for, reviewer, run):
    resp = client_for(reviewer).get(reverse("run-export", args=[run.id]))
    assert resp["Content-Type"].startswith("text/csv")
    assert "attachment" in resp["Content-Disposition"]
    rows = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))
    assert len(rows) == 4
    mismatch = next(r for r in rows if r["status"] == "amount_mismatch")
    assert mismatch["amount_difference"] == "-1500.00"


def test_csv_export_can_filter_by_status(client_for, reviewer, run):
    resp = client_for(reviewer).get(reverse("run-export", args=[run.id]), {"status": "amount_mismatch"})
    rows = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))
    assert len(rows) == 1


@pytest.mark.parametrize("raw,expected", [
    ("=1+1", "'=1+1"), ("+x", "'+x"), ("-x", "'-x"), ("@x", "'@x"), ("normal", "normal"), (None, ""),
])
def test_csv_cells_cannot_become_formulas(raw, expected):
    assert _safe(raw) == expected