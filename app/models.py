"""SQLAlchemy ORM models.

The domain mirrors a real coding workflow:

    Patient --< Encounter --< ClinicalDocument
                       |
                       +--< CodedDiagnosis  (ICD-10-CM, or ICD-10-PCS for inpatient procedures)
                       +--< CodedProcedure  (CPT/HCPCS, primarily outpatient)
                       +---- Claim --< ClaimLine

Encounter.encounter_class distinguishes inpatient vs outpatient coding, which
drives which code systems and validation rules apply.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    mrn: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    epic_fhir_id: Mapped[str | None] = mapped_column(String(128), index=True)
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    birth_date: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD
    sex: Mapped[str] = mapped_column(String(16), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    encounters: Mapped[list["Encounter"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )

    @property
    def age(self) -> int | None:
        if not self.birth_date:
            return None
        try:
            born = datetime.strptime(self.birth_date, "%Y-%m-%d")
        except ValueError:
            return None
        today = _utcnow()
        return (
            today.year
            - born.year
            - ((today.month, today.day) < (born.month, born.day))
        )


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"))
    epic_fhir_id: Mapped[str | None] = mapped_column(String(128), index=True)
    # "inpatient" or "outpatient" -> selects the coding/validation ruleset.
    encounter_class: Mapped[str] = mapped_column(String(16), default="outpatient")
    status: Mapped[str] = mapped_column(String(24), default="open")  # open|coded|billed
    place_of_service: Mapped[str | None] = mapped_column(String(8))  # POS code
    admit_date: Mapped[str | None] = mapped_column(String(10))
    discharge_date: Mapped[str | None] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    patient: Mapped[Patient] = relationship(back_populates="encounters")
    documents: Mapped[list["ClinicalDocument"]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    diagnoses: Mapped[list["CodedDiagnosis"]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    procedures: Mapped[list["CodedProcedure"]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    claim: Mapped["Claim | None"] = relationship(
        back_populates="encounter", cascade="all, delete-orphan", uselist=False
    )


class ClinicalDocument(Base):
    """Free-text clinical documentation the coder reads to assign codes."""

    __tablename__ = "clinical_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"))
    epic_fhir_id: Mapped[str | None] = mapped_column(String(128))
    doc_type: Mapped[str] = mapped_column(String(64), default="ProgressNote")
    author: Mapped[str | None] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    encounter: Mapped[Encounter] = relationship(back_populates="documents")


class CodedDiagnosis(Base):
    __tablename__ = "coded_diagnoses"

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"))
    code: Mapped[str] = mapped_column(String(16))
    system: Mapped[str] = mapped_column(String(16), default="ICD-10-CM")  # or ICD-10-PCS
    description: Mapped[str | None] = mapped_column(String(255))
    is_principal: Mapped[bool] = mapped_column(Boolean, default=False)
    present_on_admission: Mapped[str | None] = mapped_column(String(1))  # Y/N/U/W
    sequence: Mapped[int] = mapped_column(Integer, default=1)

    encounter: Mapped[Encounter] = relationship(back_populates="diagnoses")


class CodedProcedure(Base):
    __tablename__ = "coded_procedures"

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"))
    code: Mapped[str] = mapped_column(String(16))
    system: Mapped[str] = mapped_column(String(16), default="CPT")  # CPT|HCPCS
    description: Mapped[str | None] = mapped_column(String(255))
    modifiers: Mapped[str | None] = mapped_column(String(64))  # comma-separated
    units: Mapped[int] = mapped_column(Integer, default=1)
    # Pointers (1-based indices) into the encounter's diagnosis list, like the
    # CMS-1500 box 24E diagnosis pointer. Stored comma-separated.
    diagnosis_pointers: Mapped[str | None] = mapped_column(String(64))

    encounter: Mapped[Encounter] = relationship(back_populates="procedures")

    @property
    def modifier_list(self) -> list[str]:
        return [m.strip() for m in (self.modifiers or "").split(",") if m.strip()]

    @property
    def pointer_list(self) -> list[int]:
        out: list[int] = []
        for p in (self.diagnosis_pointers or "").split(","):
            p = p.strip()
            if p.isdigit():
                out.append(int(p))
        return out


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_id: Mapped[int] = mapped_column(ForeignKey("encounters.id"), unique=True)
    claim_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    claim_type: Mapped[str] = mapped_column(String(16))  # professional|institutional
    status: Mapped[str] = mapped_column(String(24), default="draft")
    total_charge: Mapped[float] = mapped_column(Float, default=0.0)
    drg_code: Mapped[str | None] = mapped_column(String(8))  # inpatient MS-DRG
    drg_description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    encounter: Mapped[Encounter] = relationship(back_populates="claim")
    lines: Mapped[list["ClaimLine"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimLine(Base):
    __tablename__ = "claim_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"))
    code: Mapped[str] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(String(255))
    modifiers: Mapped[str | None] = mapped_column(String(64))
    units: Mapped[int] = mapped_column(Integer, default=1)
    unit_charge: Mapped[float] = mapped_column(Float, default=0.0)
    line_charge: Mapped[float] = mapped_column(Float, default=0.0)
    diagnosis_pointers: Mapped[str | None] = mapped_column(String(64))

    claim: Mapped[Claim] = relationship(back_populates="lines")
