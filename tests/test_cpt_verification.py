"""Tests for single-code CPT verification."""
from app.coding import cpt
from app.coding.validator import verify_cpt


def _rules(result):
    return {i.rule for i in result.issues}


def test_format_classification():
    assert cpt.classify_format("99213") == "I"
    assert cpt.classify_format("3074F") == "II"
    assert cpt.classify_format("0042T") == "III"
    assert cpt.classify_format("J1100") == "HCPCS"
    assert cpt.classify_format("1234") is None
    assert cpt.classify_format("ABCDE") is None


def test_valid_active_code_passes():
    r = verify_cpt("99213")
    assert r.valid is True
    assert r.category == "I"
    assert not r.has_errors


def test_malformed_code_is_error():
    r = verify_cpt("ABC12")
    assert r.valid is False
    assert "FORMAT_INVALID" in _rules(r)


def test_well_formed_but_unknown_code():
    # Valid 5-digit format but not in the code set.
    r = verify_cpt("00000")
    assert r.valid is False
    assert "NOT_FOUND" in _rules(r)


def test_deleted_code_is_flagged():
    r = verify_cpt("99201")  # deleted 2021
    assert r.valid is False
    assert "DELETED_CODE" in _rules(r)


def test_sex_edit_blocks():
    # 55700 prostate biopsy on a female patient -> error.
    r = verify_cpt("55700", patient_sex="female")
    assert "SEX_EDIT" in _rules(r)
    assert r.has_errors


def test_age_edit_warns():
    # 99202 expected any age; pick a code with age window via Z00.00? Use 59510.
    r = verify_cpt("59510", patient_sex="female", patient_age=70)
    assert "AGE_EDIT" in _rules(r)


def test_pos_mismatch_warns():
    # 99223 is inpatient-only; reporting on an outpatient encounter warns.
    r = verify_cpt("99223", encounter_class="outpatient")
    assert "POS_MISMATCH" in _rules(r)


def test_modifier_unexpected_warns():
    r = verify_cpt("99213", modifiers=["62"])  # 62 not in expected list
    assert "MODIFIER_UNEXPECTED" in _rules(r)


def test_modifier_bad_format_is_error():
    r = verify_cpt("99213", modifiers=["TOOLONG"])
    assert "MODIFIER_FORMAT" in _rules(r)


def test_medical_necessity_warns_without_support():
    # 93000 ECG with an unrelated diagnosis (diabetes) -> necessity warning.
    r = verify_cpt("93000", supporting_icd=["E11.9"])
    assert "MEDICAL_NECESSITY" in _rules(r)


def test_medical_necessity_satisfied():
    r = verify_cpt("93000", supporting_icd=["R07.9"])  # chest pain supports ECG
    assert "MEDICAL_NECESSITY" not in _rules(r)
