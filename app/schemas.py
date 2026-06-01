"""Pydantic request/response models for the API layer."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Patients
# --------------------------------------------------------------------------- #
class PatientCreate(BaseModel):
    mrn: str
    first_name: str
    last_name: str
    birth_date: str | None = None
    sex: str = "unknown"
    epic_fhir_id: str | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mrn: str
    first_name: str
    last_name: str
    birth_date: str | None
    sex: str
    epic_fhir_id: str | None
    age: int | None = None


# --------------------------------------------------------------------------- #
# Encounters
# --------------------------------------------------------------------------- #
class EncounterCreate(BaseModel):
    patient_id: int
    encounter_class: str = Field("outpatient", pattern="^(inpatient|outpatient)$")
    place_of_service: str | None = None
    admit_date: str | None = None
    discharge_date: str | None = None
    reason: str | None = None


class EncounterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    encounter_class: str
    status: str
    place_of_service: str | None
    admit_date: str | None
    discharge_date: str | None
    reason: str | None
    epic_fhir_id: str | None


# --------------------------------------------------------------------------- #
# Documentation
# --------------------------------------------------------------------------- #
class DocumentCreate(BaseModel):
    doc_type: str = "ProgressNote"
    author: str | None = None
    text: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doc_type: str
    author: str | None
    text: str


# --------------------------------------------------------------------------- #
# Coding
# --------------------------------------------------------------------------- #
class DiagnosisIn(BaseModel):
    code: str
    system: str = "ICD-10-CM"
    description: str | None = None
    is_principal: bool = False
    present_on_admission: str | None = None
    sequence: int = 1


class ProcedureIn(BaseModel):
    code: str
    system: str = "CPT"
    description: str | None = None
    modifiers: list[str] = Field(default_factory=list)
    units: int = 1
    diagnosis_pointers: list[int] = Field(default_factory=list)


class CodingSubmission(BaseModel):
    diagnoses: list[DiagnosisIn] = Field(default_factory=list)
    procedures: list[ProcedureIn] = Field(default_factory=list)


class CPTVerifyRequest(BaseModel):
    code: str
    modifiers: list[str] = Field(default_factory=list)
    encounter_class: str | None = None
    patient_sex: str | None = None
    patient_age: int | None = None
    supporting_icd: list[str] | None = None


# --------------------------------------------------------------------------- #
# Epic import
# --------------------------------------------------------------------------- #
class EpicImportRequest(BaseModel):
    # In mock mode: "inpatient" | "outpatient". In real mode: Epic Encounter id.
    encounter_key: str
