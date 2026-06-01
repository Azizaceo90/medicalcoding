"""Patient CRUD endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Patient
from app.schemas import PatientCreate, PatientOut

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)) -> Patient:
    if db.scalar(select(Patient).where(Patient.mrn == payload.mrn)):
        raise HTTPException(409, f"Patient with MRN {payload.mrn} already exists.")
    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("", response_model=list[PatientOut])
def list_patients(db: Session = Depends(get_db)) -> list[Patient]:
    return list(db.scalars(select(Patient).order_by(Patient.id.desc())))


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: int, db: Session = Depends(get_db)) -> Patient:
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found.")
    return patient
