"""Tests for the inpatient utilization-review summary."""
from app.utilization import length_of_stay


def test_length_of_stay_basic():
    assert length_of_stay("2026-05-18", "2026-05-23") == 5
    assert length_of_stay("2026-05-18", "2026-05-18") == 1  # same-day -> 1
    assert length_of_stay("2026-05-18", None) is None
    assert length_of_stay(None, "2026-05-23") is None


def _setup_inpatient(client):
    imp = client.post("/api/epic/import", json={"encounter_key": "inpatient"}).json()
    enc_id = imp["encounter_id"]
    client.post(
        f"/api/coding/encounters/{enc_id}/code",
        json={
            "diagnoses": [
                {"code": "K35.80", "system": "ICD-10-CM", "is_principal": True, "sequence": 1},
                {"code": "0DTJ4ZZ", "system": "ICD-10-PCS", "sequence": 2},
            ],
            "procedures": [{"code": "99223", "diagnosis_pointers": [1]}],
        },
    )
    return enc_id


def test_summary_ready_for_submission(client):
    enc_id = _setup_inpatient(client)
    s = client.get(f"/api/utilization/encounters/{enc_id}/summary").json()

    assert s["drg"]["drg"] == "338"
    assert s["principal_diagnosis"]["code"] == "K35.80"
    # Inpatient sample admit 2026-05-18, discharge 2026-05-23 -> 5 days.
    assert s["stay"]["length_of_stay_days"] == 5
    assert s["estimated_reimbursement"] > 0
    # GMLOS for DRG 338 is 3.1, AMLOS 3.8; 5 days exceeds AMLOS -> outlier.
    assert s["length_of_stay_review"]["status"] == "outlier"
    assert s["ready_for_submission"] is True


def test_summary_lists_inpatient_only(client):
    _setup_inpatient(client)
    data = client.get("/api/utilization/inpatient-encounters").json()
    assert len(data["encounters"]) >= 1
    assert all(e for e in data["encounters"])


def test_outpatient_rejected(client):
    imp = client.post("/api/epic/import", json={"encounter_key": "outpatient"}).json()
    resp = client.get(f"/api/utilization/encounters/{imp['encounter_id']}/summary")
    assert resp.status_code == 400


def test_blocker_when_no_discharge_date(client):
    # Create an inpatient encounter with no discharge date.
    patients = client.get("/api/patients").json()
    pid = patients[0]["id"]
    enc = client.post(
        "/api/encounters",
        json={"patient_id": pid, "encounter_class": "inpatient", "admit_date": "2026-05-18"},
    ).json()
    client.post(
        f"/api/coding/encounters/{enc['id']}/code",
        json={"diagnoses": [{"code": "K35.80", "is_principal": True, "sequence": 1}], "procedures": []},
    )
    s = client.get(f"/api/utilization/encounters/{enc['id']}/summary").json()
    assert s["ready_for_submission"] is False
    assert any("Discharge date" in b for b in s["submission_blockers"])
