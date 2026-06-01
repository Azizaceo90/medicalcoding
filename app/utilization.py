"""Inpatient utilization-review summary.

Utilization management (UM) reviews an inpatient stay before/around submission
to a payer: it confirms the admission is coded, derives the working MS-DRG,
compares the actual length of stay (LOS) against the DRG benchmark (GMLOS), and
flags anything that would block a clean submission (missing principal diagnosis,
missing discharge date, LOS outliers, etc.).

This module is read-only: it summarises an existing ``Encounter`` and never
mutates it.
"""
from __future__ import annotations

from datetime import datetime

from app.billing.claims import assign_drg
from app.coding import validator
from app.models import Encounter


def _parse(d: str | None) -> datetime | None:
    if not d:
        return None
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d")
    except ValueError:
        return None


def length_of_stay(admit: str | None, discharge: str | None) -> int | None:
    """Inpatient LOS in days. Same-day admit/discharge counts as 1 day."""
    a, d = _parse(admit), _parse(discharge)
    if a is None or d is None:
        return None
    return max((d - a).days, 1)


def summarize(encounter: Encounter) -> dict:
    """Build a utilization-review summary for an inpatient encounter."""
    patient = encounter.patient

    diagnoses = sorted(
        encounter.diagnoses, key=lambda x: (not x.is_principal, x.sequence)
    )
    cm = [d for d in diagnoses if d.system == "ICD-10-CM"]
    pcs = [d for d in diagnoses if d.system == "ICD-10-PCS"]
    principal = next((d for d in cm if d.is_principal), None)

    los = length_of_stay(encounter.admit_date, encounter.discharge_date)

    # Working DRG from the coded diagnoses / procedures.
    drg = assign_drg(
        principal.code if principal else None,
        {d.code for d in cm},
        {p.code for p in pcs},
    )

    # LOS vs. the DRG geometric-mean benchmark.
    los_status = "unknown"
    los_variance: float | None = None
    if drg and drg.get("gmlos") is not None and los is not None:
        los_variance = round(los - drg["gmlos"], 1)
        if los <= drg["gmlos"]:
            los_status = "at_or_below_benchmark"
        elif los <= (drg.get("amlos") or drg["gmlos"]):
            los_status = "above_gmlos"
        else:
            los_status = "outlier"  # exceeds arithmetic mean -> review

    # Re-run coding edits so the reviewer sees blockers in one place.
    coding = validator.validate_encounter(
        encounter_class=encounter.encounter_class,
        patient_sex=patient.sex,
        patient_age=patient.age,
        diagnoses=[
            {"code": d.code, "system": d.system, "is_principal": d.is_principal, "sequence": d.sequence}
            for d in diagnoses
        ],
        procedures=[
            {"code": p.code, "modifiers": p.modifier_list, "diagnosis_pointers": p.pointer_list}
            for p in encounter.procedures
        ],
    )

    # Submission-readiness checklist.
    blockers: list[str] = []
    if encounter.encounter_class != "inpatient":
        blockers.append("Encounter is not classified as inpatient.")
    if not cm:
        blockers.append("No ICD-10-CM diagnoses are coded.")
    if principal is None:
        blockers.append("No principal diagnosis is designated.")
    if encounter.admit_date is None:
        blockers.append("Admission date is missing.")
    if encounter.discharge_date is None:
        blockers.append("Discharge date is missing (required for final submission).")
    if drg is None:
        blockers.append("No MS-DRG could be derived from the coded data.")
    if not coding["billable"]:
        blockers.append(f"Coding has {coding['error_count']} blocking edit error(s).")

    advisories: list[str] = []
    if los_status == "outlier":
        advisories.append(
            f"LOS ({los} days) exceeds the DRG arithmetic mean "
            f"({drg['amlos']} days) — high-cost/day outlier review recommended."
        )
    elif los_status == "above_gmlos":
        advisories.append(
            f"LOS ({los} days) is above the DRG geometric mean "
            f"({drg['gmlos']} days) — document continued-stay medical necessity."
        )
    if any(d.present_on_admission in (None, "") for d in cm):
        advisories.append("One or more diagnoses are missing a Present-on-Admission (POA) indicator.")

    return {
        "encounter_id": encounter.id,
        "ready_for_submission": len(blockers) == 0,
        "patient": {
            "name": f"{patient.last_name}, {patient.first_name}",
            "mrn": patient.mrn,
            "age": patient.age,
            "sex": patient.sex,
        },
        "stay": {
            "encounter_class": encounter.encounter_class,
            "admit_date": encounter.admit_date,
            "discharge_date": encounter.discharge_date,
            "length_of_stay_days": los,
            "reason": encounter.reason,
            "status": encounter.status,
        },
        "drg": drg,
        "length_of_stay_review": {
            "actual_days": los,
            "gmlos": drg.get("gmlos") if drg else None,
            "amlos": drg.get("amlos") if drg else None,
            "variance_days": los_variance,
            "status": los_status,
        },
        "principal_diagnosis": (
            {"code": principal.code, "description": principal.description}
            if principal
            else None
        ),
        "secondary_diagnoses": [
            {"code": d.code, "description": d.description, "poa": d.present_on_admission}
            for d in cm
            if not d.is_principal
        ],
        "procedures": [
            {"code": p.code, "system": p.system, "description": p.description}
            for p in pcs
        ]
        + [
            {"code": p.code, "system": p.system, "description": p.description}
            for p in encounter.procedures
        ],
        "estimated_reimbursement": drg["payment"] if drg else None,
        "coding_validation": {
            "billable": coding["billable"],
            "error_count": coding["error_count"],
            "warning_count": coding["warning_count"],
        },
        "submission_blockers": blockers,
        "advisories": advisories,
    }
