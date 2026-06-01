"""Epic FHIR integration endpoints: import an encounter, export a coded claim."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.epic import fhir
from app.models import ClinicalDocument, Encounter, Patient
from app.schemas import EpicImportRequest

router = APIRouter(prefix="/api/epic", tags=["epic"])


@router.get("/status")
def epic_status() -> dict:
    client = fhir.EpicFHIRClient()
    return {
        "mock_mode": client.mock,
        "base_url": client.base_url,
        "available_mock_scenarios": ["inpatient", "outpatient"] if client.mock else None,
    }


@router.post("/import")
def import_encounter(payload: EpicImportRequest, db: Session = Depends(get_db)) -> dict:
    """Pull a Patient + Encounter + documentation from Epic into this system."""
    client = fhir.EpicFHIRClient()
    try:
        bundle = client.fetch_encounter_bundle(payload.encounter_key)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    patient_data = fhir.map_patient(bundle["patient"])
    encounter_data = fhir.map_encounter(bundle["encounter"])

    # Upsert the patient by Epic FHIR id (fall back to MRN).
    patient = db.scalar(
        select(Patient).where(Patient.epic_fhir_id == patient_data["epic_fhir_id"])
    ) or db.scalar(select(Patient).where(Patient.mrn == patient_data["mrn"]))
    if patient is None:
        patient = Patient(**patient_data)
        db.add(patient)
        db.flush()

    encounter = Encounter(patient_id=patient.id, **encounter_data)
    db.add(encounter)
    db.flush()

    for doc_resource in bundle.get("documents", []):
        doc_data = fhir.map_document(doc_resource)
        db.add(ClinicalDocument(encounter_id=encounter.id, **doc_data))

    db.commit()
    db.refresh(encounter)
    return {
        "patient_id": patient.id,
        "encounter_id": encounter.id,
        "encounter_class": encounter.encounter_class,
        "documents_imported": len(bundle.get("documents", [])),
        "reason": encounter.reason,
    }


@router.post("/encounters/{encounter_id}/export-claim")
def export_claim(encounter_id: int, db: Session = Depends(get_db)) -> dict:
    """Render the encounter's claim as FHIR and submit it to Epic."""
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise HTTPException(404, "Encounter not found.")
    if not encounter.claim:
        raise HTTPException(409, "Generate a claim before exporting to Epic.")

    fhir_claim = fhir.build_fhir_claim(encounter.patient, encounter, encounter.claim)
    client = fhir.EpicFHIRClient()
    response = client.submit_claim(fhir_claim)
    return {"fhir_claim": fhir_claim, "epic_response": response}
