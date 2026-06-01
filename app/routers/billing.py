"""Billing endpoints: generate a claim (after validation) and read it back."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.billing import claims as billing
from app.database import get_db
from app.models import Encounter
from app.routers.coding import validate_encounter

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _serialize_claim(claim) -> dict:
    return {
        "claim_number": claim.claim_number,
        "claim_type": claim.claim_type,
        "status": claim.status,
        "total_charge": claim.total_charge,
        "drg_code": claim.drg_code,
        "drg_description": claim.drg_description,
        "lines": [
            {
                "code": line.code,
                "description": line.description,
                "modifiers": line.modifiers,
                "units": line.units,
                "unit_charge": line.unit_charge,
                "line_charge": line.line_charge,
                "diagnosis_pointers": line.diagnosis_pointers,
            }
            for line in claim.lines
        ],
    }


@router.post("/encounters/{encounter_id}/claim")
def create_claim(encounter_id: int, db: Session = Depends(get_db)) -> dict:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise HTTPException(404, "Encounter not found.")

    # Coding edits must pass before a claim can be produced.
    validation = validate_encounter(encounter_id, db)
    if not validation["billable"]:
        raise HTTPException(
            422,
            detail={
                "message": "Coding has blocking errors; resolve them before billing.",
                "validation": validation,
            },
        )

    claim = billing.generate_claim(db, encounter)
    db.commit()
    db.refresh(claim)
    return {"validation": validation, "claim": _serialize_claim(claim)}


@router.get("/encounters/{encounter_id}/claim")
def get_claim(encounter_id: int, db: Session = Depends(get_db)) -> dict:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise HTTPException(404, "Encounter not found.")
    if not encounter.claim:
        raise HTTPException(404, "No claim has been generated for this encounter.")
    return _serialize_claim(encounter.claim)
