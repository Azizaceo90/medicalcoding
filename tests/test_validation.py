"""Tests for whole-encounter validation, NCCI bundling, and ICD checks."""
from app.coding.validator import check_ncci, validate_encounter


def _global_rules(v):
    return {i["rule"] for i in v["global_issues"]}


def _all_result_rules(v):
    return {i["rule"] for r in v["results"] for i in r["issues"]}


def test_ncci_bundled_pair_is_error():
    issues = check_ncci(
        [{"code": "93000", "modifiers": []}, {"code": "93010", "modifiers": []}]
    )
    assert any(i.rule == "NCCI_BUNDLED" and i.severity == "error" for i in issues)


def test_ncci_bypass_modifier_downgrades_to_info():
    issues = check_ncci(
        [{"code": "44970", "modifiers": []}, {"code": "44950", "modifiers": ["59"]}]
    )
    assert any(i.rule == "NCCI_BYPASSED" for i in issues)
    assert not any(i.rule == "NCCI_BUNDLED" for i in issues)


def test_outpatient_clean_claim_is_billable():
    v = validate_encounter(
        encounter_class="outpatient",
        patient_sex="male",
        patient_age=58,
        diagnoses=[{"code": "R07.9", "system": "ICD-10-CM", "is_principal": True}],
        procedures=[{"code": "93000", "modifiers": [], "diagnosis_pointers": [1]}],
    )
    assert v["billable"] is True
    assert v["error_count"] == 0


def test_missing_principal_inpatient_is_error():
    v = validate_encounter(
        encounter_class="inpatient",
        patient_sex="female",
        patient_age=74,
        diagnoses=[{"code": "K35.80", "system": "ICD-10-CM", "is_principal": False}],
        procedures=[],
    )
    assert "NO_PRINCIPAL_DX" in _global_rules(v)
    assert v["billable"] is False


def test_pcs_on_outpatient_is_error():
    v = validate_encounter(
        encounter_class="outpatient",
        patient_sex="female",
        patient_age=74,
        diagnoses=[
            {"code": "K35.80", "system": "ICD-10-CM", "is_principal": True},
            {"code": "0DTJ4ZZ", "system": "ICD-10-PCS", "is_principal": False},
        ],
        procedures=[],
    )
    assert "PCS_OUTPATIENT" in _all_result_rules(v)
    assert v["billable"] is False


def test_nonbillable_header_dx_is_error():
    v = validate_encounter(
        encounter_class="outpatient",
        patient_sex="male",
        patient_age=40,
        diagnoses=[{"code": "M54.5", "system": "ICD-10-CM", "is_principal": True}],
        procedures=[],
    )
    assert "NONBILLABLE_DX" in _all_result_rules(v)


def test_procedure_without_pointer_warns():
    v = validate_encounter(
        encounter_class="outpatient",
        patient_sex="male",
        patient_age=58,
        diagnoses=[{"code": "R07.9", "system": "ICD-10-CM", "is_principal": True}],
        procedures=[{"code": "93000", "modifiers": [], "diagnosis_pointers": []}],
    )
    assert "NO_DX_POINTER" in _all_result_rules(v)
    # warning only -> still billable
    assert v["billable"] is True
