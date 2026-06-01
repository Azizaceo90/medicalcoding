"""Encounter and clinical-documentation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ClinicalDocument, Encounter, Patient
from app.schemas import (
    DocumentCreate,
    DocumentOut,
    EncounterCreate,
    EncounterOut,
)

router = APIRouter(prefix="/api/encounters", tags=["encounters"])


@router.post("", response_model=EncounterOut, status_code=201)
def create_encounter(payload: EncounterCreate, db: Session = Depends(get_db)) -> Encounter:
    if not db.get(Patient, payload.patient_id):
        raise HTTPException(404, "Patient not found.")
    encounter = Encounter(**payload.model_dump())
    db.add(encounter)
    db.commit()
    db.refresh(encounter)
    return encounter


@router.get("", response_model=list[EncounterOut])
def list_encounters(
    patient_id: int | None = None, db: Session = Depends(get_db)
) -> list[Encounter]:
    stmt = select(Encounter).order_by(Encounter.id.desc())
    if patient_id is not None:
        stmt = stmt.where(Encounter.patient_id == patient_id)
    return list(db.scalars(stmt))


@router.get("/{encounter_id}", response_model=EncounterOut)
def get_encounter(encounter_id: int, db: Session = Depends(get_db)) -> Encounter:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise HTTPException(404, "Encounter not found.")
    return encounter


@router.post("/{encounter_id}/documents", response_model=DocumentOut, status_code=201)
def add_document(
    encounter_id: int, payload: DocumentCreate, db: Session = Depends(get_db)
) -> ClinicalDocument:
    if not db.get(Encounter, encounter_id):
        raise HTTPException(404, "Encounter not found.")
    doc = ClinicalDocument(encounter_id=encounter_id, **payload.model_dump())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/{encounter_id}/documents", response_model=list[DocumentOut])
def list_documents(encounter_id: int, db: Session = Depends(get_db)) -> list[ClinicalDocument]:
    if not db.get(Encounter, encounter_id):
        raise HTTPException(404, "Encounter not found.")
    return list(
        db.scalars(
            select(ClinicalDocument).where(ClinicalDocument.encounter_id == encounter_id)
        )
    )
