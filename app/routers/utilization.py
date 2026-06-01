"""Inpatient utilization-review endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import utilization
from app.database import get_db
from app.models import Encounter

router = APIRouter(prefix="/api/utilization", tags=["utilization"])


@router.get("/inpatient-encounters")
def list_inpatient_encounters(db: Session = Depends(get_db)) -> dict:
    """List inpatient encounters with a one-line utilization snapshot each."""
    encounters = db.scalars(
        select(Encounter)
        .where(Encounter.encounter_class == "inpatient")
        .order_by(Encounter.id.desc())
    )
    items = []
    for enc in encounters:
        s = utilization.summarize(enc)
        items.append(
            {
                "encounter_id": enc.id,
                "patient": s["patient"]["name"],
                "mrn": s["patient"]["mrn"],
                "drg": s["drg"]["drg"] if s["drg"] else None,
                "length_of_stay_days": s["stay"]["length_of_stay_days"],
                "los_status": s["length_of_stay_review"]["status"],
                "ready_for_submission": s["ready_for_submission"],
            }
        )
    return {"encounters": items}


@router.get("/encounters/{encounter_id}/summary")
def utilization_summary(encounter_id: int, db: Session = Depends(get_db)) -> dict:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise HTTPException(404, "Encounter not found.")
    if encounter.encounter_class != "inpatient":
        raise HTTPException(
            400, "Utilization review applies to inpatient encounters only."
        )
    return utilization.summarize(encounter)
