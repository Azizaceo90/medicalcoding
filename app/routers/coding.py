"""Coding endpoints: code search, CPT verification, coding submission & validation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.coding import cpt as cpt_lib
from app.coding import icd as icd_lib
from app.coding import validator
from app.database import get_db
from app.models import CodedDiagnosis, CodedProcedure, Encounter
from app.schemas import CodingSubmission, CPTVerifyRequest

router = APIRouter(prefix="/api/coding", tags=["coding"])


# --------------------------------------------------------------------------- #
# Reference lookups
# --------------------------------------------------------------------------- #
@router.get("/search/icd")
def search_icd(q: str = Query(..., min_length=1)) -> dict:
    return {"results": icd_lib.search(q)}


@router.get("/search/cpt")
def search_cpt(q: str = Query(..., min_length=1)) -> dict:
    return {"results": cpt_lib.search(q)}


# --------------------------------------------------------------------------- #
# CPT verification (single code) — the core requested capability
# --------------------------------------------------------------------------- #
@router.post("/verify-cpt")
def verify_cpt(payload: CPTVerifyRequest) -> dict:
    result = validator.verify_cpt(
        payload.code,
        modifiers=payload.modifiers,
        encounter_class=payload.encounter_class,
        patient_sex=payload.patient_sex,
        patient_age=payload.patient_age,
        supporting_icd=payload.supporting_icd,
    )
    return result.dict()


# --------------------------------------------------------------------------- #
# Persist coding for an encounter, then validate the whole encounter
# --------------------------------------------------------------------------- #
@router.post("/encounters/{encounter_id}/code")
def submit_coding(
    encounter_id: int, payload: CodingSubmission, db: Session = Depends(get_db)
) -> dict:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise HTTPException(404, "Encounter not found.")

    # Replace existing coding so the operation is idempotent.
    for existing in list(encounter.diagnoses):
        db.delete(existing)
    for existing in list(encounter.procedures):
        db.delete(existing)
    db.flush()

    for dx in payload.diagnoses:
        # Auto-fill description from the code set when the caller omitted it.
        desc = dx.description
        if desc is None:
            row = (
                icd_lib.lookup_pcs(dx.code)
                if dx.system == "ICD-10-PCS"
                else icd_lib.lookup_cm(dx.code)
            )
            desc = row["description"] if row else None
        db.add(
            CodedDiagnosis(
                encounter_id=encounter_id,
                code=dx.code.strip().upper(),
                system=dx.system,
                description=desc,
                is_principal=dx.is_principal,
                present_on_admission=dx.present_on_admission,
                sequence=dx.sequence,
            )
        )

    for proc in payload.procedures:
        desc = proc.description
        if desc is None:
            row = cpt_lib.lookup(proc.code)
            desc = row["short"] if row else None
        db.add(
            CodedProcedure(
                encounter_id=encounter_id,
                code=proc.code.strip().upper(),
                system=proc.system,
                description=desc,
                modifiers=",".join(proc.modifiers),
                units=proc.units,
                diagnosis_pointers=",".join(str(p) for p in proc.diagnosis_pointers),
            )
        )

    encounter.status = "coded"
    db.commit()
    # expire_on_commit is off, so the cached (empty) relationship lists must be
    # refreshed before validation reads them back.
    db.refresh(encounter)
    return validate_encounter(encounter_id, db)


@router.get("/encounters/{encounter_id}/validate")
def validate_encounter(encounter_id: int, db: Session = Depends(get_db)) -> dict:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise HTTPException(404, "Encounter not found.")
    patient = encounter.patient

    diagnoses = [
        {
            "code": d.code,
            "system": d.system,
            "is_principal": d.is_principal,
            "sequence": d.sequence,
        }
        for d in encounter.diagnoses
    ]
    procedures = [
        {
            "code": p.code,
            "modifiers": p.modifier_list,
            "diagnosis_pointers": p.pointer_list,
        }
        for p in encounter.procedures
    ]

    return validator.validate_encounter(
        encounter_class=encounter.encounter_class,
        patient_sex=patient.sex,
        patient_age=patient.age,
        diagnoses=diagnoses,
        procedures=procedures,
    )
