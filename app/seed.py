"""Seed the database with fully-coded fake patients, encounters, and claims.

Run standalone::

    python -m app.seed

Or let it run automatically: ``app.main`` calls :func:`seed_if_empty` on startup
so a freshly deployed instance shows working data immediately. Set
``SEED_ON_STARTUP=false`` to disable that.

All patients/notes here are fictitious and for testing only.
"""
from __future__ import annotations

from sqlalchemy import select

from app.billing import claims as billing
from app.database import SessionLocal, init_db
from app.models import (
    ClinicalDocument,
    CodedDiagnosis,
    CodedProcedure,
    Encounter,
    Patient,
)

# --------------------------------------------------------------------------- #
# Fake case definitions
# --------------------------------------------------------------------------- #
# Each case is a self-contained patient + encounter + documentation + coding.
# "principal" marks the principal diagnosis; procedure "ptr" values are 1-based
# pointers into that case's diagnosis list.
CASES: list[dict] = [
    # ---- Outpatient ----------------------------------------------------- #
    {
        "patient": {"mrn": "MRN-100245", "first_name": "Marcus", "last_name": "Stone",
                    "birth_date": "1968-04-12", "sex": "male", "epic_fhir_id": "eXyZ-OUTPT-001"},
        "encounter": {"encounter_class": "outpatient", "place_of_service": "11",
                      "admit_date": "2026-05-20", "reason": "Chest pain, rule out cardiac cause"},
        "documents": [{"doc_type": "Progress Note", "author": "Dr. A. Patel",
                       "text": "58M established patient, intermittent chest pain x3 days. Moderate MDM. "
                               "12-lead ECG interpreted: no acute ST changes. Assessment: chest pain "
                               "(R07.9), hypertension (I10). ~35 minutes."}],
        "diagnoses": [{"code": "R07.9", "principal": True}, {"code": "I10"}],
        "procedures": [{"code": "99214", "modifiers": ["25"], "ptr": [1, 2]},
                       {"code": "93000", "ptr": [1]}],
    },
    {
        "patient": {"mrn": "MRN-100512", "first_name": "Diane", "last_name": "Foster",
                    "birth_date": "1972-11-03", "sex": "female"},
        "encounter": {"encounter_class": "outpatient", "place_of_service": "11",
                      "admit_date": "2026-05-22", "reason": "Type 2 diabetes follow-up"},
        "documents": [{"doc_type": "Progress Note", "author": "Dr. L. Kim",
                       "text": "53F with type 2 diabetes (E11.65, hyperglycemia) and hypertension (I10). "
                               "Comprehensive metabolic panel and CBC ordered. Established patient, low MDM."}],
        "diagnoses": [{"code": "E11.65", "principal": True}, {"code": "I10"}],
        "procedures": [{"code": "99213", "ptr": [1, 2]},
                       {"code": "80053", "ptr": [1]},
                       {"code": "85025", "ptr": [1]}],
    },
    {
        "patient": {"mrn": "MRN-100783", "first_name": "Harold", "last_name": "Briggs",
                    "birth_date": "1955-02-19", "sex": "male"},
        "encounter": {"encounter_class": "outpatient", "place_of_service": "22",
                      "admit_date": "2026-05-25", "reason": "Elevated PSA, prostate biopsy"},
        "documents": [{"doc_type": "Procedure Note", "author": "Dr. S. Rao",
                       "text": "71M with benign prostatic hyperplasia (N40.0) and elevated PSA. "
                               "Transrectal needle biopsy of prostate performed."}],
        "diagnoses": [{"code": "N40.0", "principal": True}],
        "procedures": [{"code": "55700", "ptr": [1]}],
    },
    # ---- Inpatient ------------------------------------------------------ #
    {
        "patient": {"mrn": "MRN-200871", "first_name": "Linda", "last_name": "Howard",
                    "birth_date": "1951-09-30", "sex": "female", "epic_fhir_id": "eXyZ-INPT-001"},
        "encounter": {"encounter_class": "inpatient", "place_of_service": "21",
                      "admit_date": "2026-05-18", "discharge_date": "2026-05-23",
                      "reason": "Acute appendicitis"},
        "documents": [{"doc_type": "Discharge Summary", "author": "Dr. R. Nguyen",
                       "text": "74F admitted with acute appendicitis (K35.80). Laparoscopic appendectomy "
                               "(0DTJ4ZZ). Uncomplicated. Discharged day 5, stable."}],
        "diagnoses": [{"code": "K35.80", "principal": True, "poa": "Y"},
                      {"code": "0DTJ4ZZ", "system": "ICD-10-PCS"}],
        "procedures": [{"code": "99223", "ptr": [1]}],
    },
    {
        "patient": {"mrn": "MRN-200934", "first_name": "Robert", "last_name": "Chen",
                    "birth_date": "1958-07-14", "sex": "male"},
        "encounter": {"encounter_class": "inpatient", "place_of_service": "21",
                      "admit_date": "2026-05-19", "discharge_date": "2026-05-23",
                      "reason": "Acute heart failure exacerbation"},
        "documents": [{"doc_type": "Discharge Summary", "author": "Dr. M. Owens",
                       "text": "68M admitted with decompensated heart failure (I50.9) on background "
                               "hypertension (I10). Diuresed, ECG and labs monitored. Discharged day 4."}],
        "diagnoses": [{"code": "I50.9", "principal": True, "poa": "Y"},
                      {"code": "I10", "poa": "Y"}],
        "procedures": [{"code": "99223", "ptr": [1]},
                       {"code": "93010", "ptr": [1]},
                       {"code": "80053", "ptr": [1]}],
    },
    {
        "patient": {"mrn": "MRN-201088", "first_name": "Maria", "last_name": "Garcia",
                    "birth_date": "1967-03-08", "sex": "female"},
        "encounter": {"encounter_class": "inpatient", "place_of_service": "21",
                      "admit_date": "2026-05-15", "discharge_date": "2026-05-21",
                      "reason": "Community-acquired pneumonia"},
        "documents": [{"doc_type": "Discharge Summary", "author": "Dr. T. Brooks",
                       "text": "59F admitted with pneumonia (J18.9). Chest x-ray and CBC obtained. "
                               "IV antibiotics. Prolonged course, discharged day 6."}],
        "diagnoses": [{"code": "J18.9", "principal": True, "poa": "Y"}],
        "procedures": [{"code": "99223", "ptr": [1]},
                       {"code": "71046", "ptr": [1]},
                       {"code": "85025", "ptr": [1]}],
    },
    {
        "patient": {"mrn": "MRN-201145", "first_name": "James", "last_name": "Wilson",
                    "birth_date": "1954-12-01", "sex": "male"},
        "encounter": {"encounter_class": "inpatient", "place_of_service": "21",
                      "admit_date": "2026-05-24", "discharge_date": "2026-05-28",
                      "reason": "NSTEMI"},
        "documents": [{"doc_type": "Discharge Summary", "author": "Dr. P. Adler",
                       "text": "71M admitted with NSTEMI (I21.4). Serial ECGs and cardiac monitoring. "
                               "Medically managed. Discharged day 4 on guideline-directed therapy."}],
        "diagnoses": [{"code": "I21.4", "principal": True, "poa": "Y"},
                      {"code": "I10", "poa": "Y"}],
        "procedures": [{"code": "99223", "ptr": [1]},
                       {"code": "93010", "ptr": [1]}],
    },
]


def _build_case(db, case: dict) -> int:
    """Create one patient/encounter/coding/claim from a case definition."""
    pdata = case["patient"]
    patient = db.scalar(select(Patient).where(Patient.mrn == pdata["mrn"]))
    if patient is None:
        patient = Patient(**pdata)
        db.add(patient)
        db.flush()

    encounter = Encounter(patient_id=patient.id, status="coded", **case["encounter"])
    db.add(encounter)
    db.flush()

    for doc in case.get("documents", []):
        db.add(ClinicalDocument(encounter_id=encounter.id, **doc))

    for seq, dx in enumerate(case["diagnoses"], start=1):
        from app.coding import icd as icd_lib

        system = dx.get("system", "ICD-10-CM")
        row = icd_lib.lookup_pcs(dx["code"]) if system == "ICD-10-PCS" else icd_lib.lookup_cm(dx["code"])
        db.add(
            CodedDiagnosis(
                encounter_id=encounter.id,
                code=dx["code"],
                system=system,
                description=row["description"] if row else None,
                is_principal=dx.get("principal", False),
                present_on_admission=dx.get("poa"),
                sequence=seq,
            )
        )

    for proc in case.get("procedures", []):
        from app.coding import cpt as cpt_lib

        row = cpt_lib.lookup(proc["code"])
        db.add(
            CodedProcedure(
                encounter_id=encounter.id,
                code=proc["code"],
                system="CPT",
                description=row["short"] if row else None,
                modifiers=",".join(proc.get("modifiers", [])),
                diagnosis_pointers=",".join(str(p) for p in proc.get("ptr", [])),
            )
        )

    db.flush()
    db.refresh(encounter)
    # Generate a claim so billing/utilization pages have content.
    billing.generate_claim(db, encounter)
    return encounter.id


def seed() -> list[int]:
    """Create all fake cases. Idempotent per patient MRN."""
    init_db()
    ids: list[int] = []
    with SessionLocal() as db:
        for case in CASES:
            ids.append(_build_case(db, case))
        db.commit()
    return ids


def seed_if_empty() -> list[int]:
    """Seed only when there are no patients yet (safe to call on every startup)."""
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(Patient.id).limit(1)) is not None:
            return []
    return seed()


if __name__ == "__main__":
    ids = seed()
    print(f"Seeded {len(ids)} encounters: {ids}")
