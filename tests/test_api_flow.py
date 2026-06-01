"""End-to-end API test: Epic import -> code -> verify -> validate -> bill -> export."""


def test_full_outpatient_pipeline(client):
    # 1. Import an outpatient case from the Epic mock.
    imp = client.post("/api/epic/import", json={"encounter_key": "outpatient"}).json()
    enc_id = imp["encounter_id"]
    assert imp["encounter_class"] == "outpatient"
    assert imp["documents_imported"] >= 1

    # 2. Verify a CPT code standalone.
    v = client.post(
        "/api/coding/verify-cpt",
        json={"code": "93000", "supporting_icd": ["R07.9"]},
    ).json()
    assert v["valid"] is True

    # 3. Submit coding (chest pain + ECG + E/M).
    coding = {
        "diagnoses": [
            {"code": "R07.9", "system": "ICD-10-CM", "is_principal": True, "sequence": 1},
            {"code": "I10", "system": "ICD-10-CM", "sequence": 2},
        ],
        "procedures": [
            {"code": "99214", "modifiers": ["25"], "diagnosis_pointers": [1, 2]},
            {"code": "93000", "diagnosis_pointers": [1]},
        ],
    }
    val = client.post(f"/api/coding/encounters/{enc_id}/code", json=coding).json()
    assert val["billable"] is True, val

    # 4. Generate the professional claim.
    bill = client.post(f"/api/billing/encounters/{enc_id}/claim").json()
    claim = bill["claim"]
    assert claim["claim_type"] == "professional"
    assert claim["total_charge"] > 0
    assert len(claim["lines"]) == 2

    # 5. Export as a FHIR Claim to Epic.
    exp = client.post(f"/api/epic/encounters/{enc_id}/export-claim").json()
    assert exp["fhir_claim"]["resourceType"] == "Claim"
    assert exp["epic_response"]["outcome"] == "complete"


def test_inpatient_pipeline_assigns_drg(client):
    imp = client.post("/api/epic/import", json={"encounter_key": "inpatient"}).json()
    enc_id = imp["encounter_id"]
    assert imp["encounter_class"] == "inpatient"

    coding = {
        "diagnoses": [
            {"code": "K35.80", "system": "ICD-10-CM", "is_principal": True, "sequence": 1},
            {"code": "0DTJ4ZZ", "system": "ICD-10-PCS", "sequence": 2},
        ],
        "procedures": [
            {"code": "99223", "diagnosis_pointers": [1]},
        ],
    }
    val = client.post(f"/api/coding/encounters/{enc_id}/code", json=coding).json()
    assert val["billable"] is True, val

    bill = client.post(f"/api/billing/encounters/{enc_id}/claim").json()
    claim = bill["claim"]
    assert claim["claim_type"] == "institutional"
    assert claim["drg_code"] == "338"
    assert claim["total_charge"] > 0


def test_billing_blocked_by_errors(client):
    imp = client.post("/api/epic/import", json={"encounter_key": "outpatient"}).json()
    enc_id = imp["encounter_id"]
    # Deleted CPT code -> blocking error -> billing must 422.
    coding = {
        "diagnoses": [{"code": "R07.9", "is_principal": True, "sequence": 1}],
        "procedures": [{"code": "99201", "diagnosis_pointers": [1]}],
    }
    val = client.post(f"/api/coding/encounters/{enc_id}/code", json=coding).json()
    assert val["billable"] is False
    resp = client.post(f"/api/billing/encounters/{enc_id}/claim")
    assert resp.status_code == 422
