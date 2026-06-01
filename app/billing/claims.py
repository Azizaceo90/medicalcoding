"""Claim assembly.

Outpatient encounters generate a *professional* claim (CMS-1500 / 837P style):
one line per CPT/HCPCS procedure, priced from the fee schedule.

Inpatient encounters generate an *institutional* claim (UB-04 / 837I style):
reimbursement is driven by an MS-DRG derived from the principal diagnosis and
any procedures, rather than line-item CPT pricing.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.coding import cpt as cpt_lib
from app.config import settings
from app.models import Claim, ClaimLine, Encounter

# A tiny illustrative MS-DRG grouper keyed on principal ICD-10-CM / PCS codes.
# Real grouping uses the full CMS GROUPER with CC/MCC severity logic.
_DRG_RULES: list[dict] = [
    {"match_dx": {"I21.4"}, "drg": "280", "desc": "Acute MI, discharged alive w/ MCC", "weight": 1.7289},
    {"match_dx": {"I50.9"}, "drg": "291", "desc": "Heart failure & shock w/ MCC", "weight": 1.3454},
    {"match_dx": {"J18.9", "J44.1"}, "drg": "193", "desc": "Simple pneumonia & pleurisy w/ MCC", "weight": 1.4185},
    {"match_dx": {"K35.80"}, "drg": "338", "desc": "Appendectomy w/o complicated principal dx", "weight": 1.6478},
    {"match_pcs": {"0SR9019"}, "drg": "470", "desc": "Major hip/knee joint replacement w/o MCC", "weight": 1.9871},
    {"match_dx": {"O80"}, "drg": "807", "desc": "Vaginal delivery w/o sterilization", "weight": 0.5934},
]
_DRG_BASE_RATE = 6500.0  # illustrative hospital base payment rate (USD)


def assign_drg(principal_dx: str | None, dx_codes: set[str], pcs_codes: set[str]) -> dict | None:
    """Return an MS-DRG assignment for an inpatient stay, or None."""
    all_dx = set(dx_codes)
    if principal_dx:
        all_dx.add(principal_dx)
    for rule in _DRG_RULES:
        if rule.get("match_pcs", set()) & pcs_codes:
            return _drg_payload(rule)
        if rule.get("match_dx", set()) & all_dx:
            return _drg_payload(rule)
    return None


def _drg_payload(rule: dict) -> dict:
    return {
        "drg": rule["drg"],
        "description": rule["desc"],
        "weight": rule["weight"],
        "payment": round(rule["weight"] * _DRG_BASE_RATE, 2),
    }


def _line_charge(code: str, encounter_class: str, units: int) -> float:
    """Price one procedure line from the fee schedule (or RVU fallback)."""
    row = cpt_lib.lookup(code)
    if not row:
        return 0.0
    rate_key = "facility_rate" if encounter_class == "inpatient" else "nonfacility_rate"
    rate = row.get(rate_key) or row.get("facility_rate") or 0.0
    if rate == 0.0 and row.get("wrvu"):
        rate = round(row["wrvu"] * settings.MEDICARE_CONVERSION_FACTOR, 2)
    return round(rate * max(units, 1), 2)


def generate_claim(db: Session, encounter: Encounter) -> Claim:
    """Build (or rebuild) the claim for an encounter and persist it.

    Caller is responsible for having validated the coding first; this function
    assembles charges and DRG but does not re-run edits.
    """
    # Replace any existing claim so regeneration is idempotent.
    if encounter.claim is not None:
        db.delete(encounter.claim)
        db.flush()

    is_inpatient = encounter.encounter_class == "inpatient"
    claim = Claim(
        encounter_id=encounter.id,
        claim_number=f"CLM-{uuid.uuid4().hex[:10].upper()}",
        claim_type="institutional" if is_inpatient else "professional",
        status="draft",
    )

    total = 0.0
    for proc in encounter.procedures:
        unit_charge = _line_charge(proc.code, encounter.encounter_class, 1)
        line_charge = round(unit_charge * max(proc.units, 1), 2)
        total += line_charge
        claim.lines.append(
            ClaimLine(
                code=proc.code,
                description=proc.description,
                modifiers=proc.modifiers,
                units=proc.units,
                unit_charge=unit_charge,
                line_charge=line_charge,
                diagnosis_pointers=proc.diagnosis_pointers,
            )
        )

    if is_inpatient:
        dx_codes = {d.code for d in encounter.diagnoses if d.system == "ICD-10-CM"}
        pcs_codes = {d.code for d in encounter.diagnoses if d.system == "ICD-10-PCS"}
        principal = next((d.code for d in encounter.diagnoses if d.is_principal), None)
        drg = assign_drg(principal, dx_codes, pcs_codes)
        if drg:
            claim.drg_code = drg["drg"]
            claim.drg_description = drg["description"]
            # For inpatient, the DRG payment is the expected reimbursement.
            total = drg["payment"]

    claim.total_charge = round(total, 2)
    db.add(claim)
    encounter.status = "billed"
    db.flush()
    return claim
