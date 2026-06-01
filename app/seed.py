"""Seed the database with the two Epic mock scenarios (inpatient + outpatient).

Run standalone::

    python -m app.seed

Idempotent: existing patients (matched by Epic FHIR id / MRN) are reused.
"""
from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.epic import fhir
from app.models import ClinicalDocument, Encounter, Patient


def seed() -> list[int]:
    init_db()
    client = fhir.EpicFHIRClient(mock=True)
    created_encounters: list[int] = []

    with SessionLocal() as db:
        for scenario in ("outpatient", "inpatient"):
            bundle = client.fetch_encounter_bundle(scenario)
            pdata = fhir.map_patient(bundle["patient"])
            edata = fhir.map_encounter(bundle["encounter"])

            patient = db.scalar(
                select(Patient).where(Patient.epic_fhir_id == pdata["epic_fhir_id"])
            )
            if patient is None:
                patient = Patient(**pdata)
                db.add(patient)
                db.flush()

            encounter = Encounter(patient_id=patient.id, **edata)
            db.add(encounter)
            db.flush()
            for doc in bundle["documents"]:
                db.add(ClinicalDocument(encounter_id=encounter.id, **fhir.map_document(doc)))

            created_encounters.append(encounter.id)
        db.commit()

    return created_encounters


if __name__ == "__main__":
    ids = seed()
    print(f"Seeded encounters: {ids}")
