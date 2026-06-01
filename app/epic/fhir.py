"""Epic FHIR R4 client and resource mappers.

Epic exposes patient data through the FHIR R4 API and authenticates with the
SMART-on-FHIR OAuth2 *client_credentials* (backend services) flow. This module:

  * obtains a bearer token (real mode) from ``EPIC_TOKEN_URL``;
  * pulls Patient / Encounter / Condition / DocumentReference resources;
  * maps them into this system's internal domain dicts; and
  * builds an outbound FHIR ``Claim`` resource from a coded encounter.

When ``EPIC_MOCK_MODE`` is true (the default) no network calls are made and
deterministic sample resources are returned, so the whole pipeline — import,
code, verify, bill, export — can be demonstrated and tested offline.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.models import Claim, Encounter, Patient

FHIR_ICD10_CM = "http://hl7.org/fhir/sid/icd-10-cm"
FHIR_CPT = "http://www.ama-assn.org/go/cpt"


# --------------------------------------------------------------------------- #
# Sample data used in mock mode
# --------------------------------------------------------------------------- #
_SAMPLE_BUNDLE: dict[str, dict] = {
    "outpatient": {
        "patient": {
            "resourceType": "Patient",
            "id": "eXyZ-OUTPT-001",
            "name": [{"family": "Stone", "given": ["Marcus"]}],
            "gender": "male",
            "birthDate": "1968-04-12",
            "identifier": [{"system": "urn:oid:1.2.840.MRN", "value": "MRN-100245"}],
        },
        "encounter": {
            "resourceType": "Encounter",
            "id": "eENC-OUTPT-001",
            "class": {"code": "AMB", "display": "ambulatory"},
            "period": {"start": "2026-05-20"},
            "reasonCode": [{"text": "Chest pain, rule out cardiac cause"}],
        },
        "documents": [
            {
                "resourceType": "DocumentReference",
                "id": "eDOC-OUTPT-001",
                "type": {"text": "Progress Note"},
                "author": [{"display": "Dr. A. Patel"}],
                "content_text": (
                    "Established patient, 58M, presents with intermittent chest "
                    "pain x3 days. Moderate complexity MDM. ECG with 12 leads "
                    "obtained and interpreted: no acute ST changes. CMP and CBC "
                    "ordered. Assessment: chest pain (R07.9), essential "
                    "hypertension (I10). Plan: stress test, continue "
                    "antihypertensives. ~35 minutes spent."
                ),
            }
        ],
    },
    "inpatient": {
        "patient": {
            "resourceType": "Patient",
            "id": "eXyZ-INPT-001",
            "name": [{"family": "Howard", "given": ["Linda"]}],
            "gender": "female",
            "birthDate": "1951-09-30",
            "identifier": [{"system": "urn:oid:1.2.840.MRN", "value": "MRN-200871"}],
        },
        "encounter": {
            "resourceType": "Encounter",
            "id": "eENC-INPT-001",
            "class": {"code": "IMP", "display": "inpatient"},
            "period": {"start": "2026-05-18", "end": "2026-05-23"},
            "reasonCode": [{"text": "Acute appendicitis"}],
        },
        "documents": [
            {
                "resourceType": "DocumentReference",
                "id": "eDOC-INPT-001",
                "type": {"text": "Discharge Summary"},
                "author": [{"display": "Dr. R. Nguyen"}],
                "content_text": (
                    "74F admitted with acute appendicitis (K35.80). Underwent "
                    "laparoscopic appendectomy (resection of appendix, "
                    "percutaneous endoscopic approach — 0DTJ4ZZ). Post-op course "
                    "uncomplicated. CBC monitored. Discharged home day 5 in "
                    "stable condition."
                ),
            }
        ],
    },
}


class EpicFHIRClient:
    """Thin Epic FHIR R4 client supporting a real and a mock transport."""

    def __init__(self, *, mock: bool | None = None) -> None:
        self.mock = settings.EPIC_MOCK_MODE if mock is None else mock
        self.base_url = settings.EPIC_FHIR_BASE_URL.rstrip("/")
        self._token: str | None = None

    # -- auth ------------------------------------------------------------- #
    def _get_token(self) -> str:
        if self.mock:
            return "mock-token"
        if self._token:
            return self._token
        resp = httpx.post(
            settings.EPIC_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.EPIC_CLIENT_ID,
                "client_secret": settings.EPIC_CLIENT_SECRET,
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/fhir+json",
        }

    # -- reads ------------------------------------------------------------ #
    def fetch_encounter_bundle(self, key: str) -> dict[str, Any]:
        """Return {patient, encounter, documents} for an encounter.

        In mock mode ``key`` selects a canned scenario ('inpatient' or
        'outpatient'). In real mode ``key`` is an Epic Encounter FHIR id and the
        related Patient + DocumentReference resources are fetched alongside it.
        """
        if self.mock:
            scenario = _SAMPLE_BUNDLE.get(key)
            if scenario is None:
                raise KeyError(
                    f"Unknown mock scenario '{key}'. "
                    f"Use one of: {', '.join(_SAMPLE_BUNDLE)}."
                )
            return scenario

        enc = httpx.get(
            f"{self.base_url}/Encounter/{key}", headers=self._headers(), timeout=30
        )
        enc.raise_for_status()
        encounter = enc.json()
        patient_ref = encounter.get("subject", {}).get("reference", "").split("/")[-1]
        pat = httpx.get(
            f"{self.base_url}/Patient/{patient_ref}",
            headers=self._headers(),
            timeout=30,
        )
        pat.raise_for_status()
        docs = httpx.get(
            f"{self.base_url}/DocumentReference",
            params={"encounter": f"Encounter/{key}"},
            headers=self._headers(),
            timeout=30,
        )
        docs.raise_for_status()
        documents = [e["resource"] for e in docs.json().get("entry", [])]
        return {"patient": pat.json(), "encounter": encounter, "documents": documents}

    # -- writes ----------------------------------------------------------- #
    def submit_claim(self, fhir_claim: dict) -> dict:
        """POST a FHIR Claim resource to Epic (or echo it back in mock mode)."""
        if self.mock:
            return {
                "resourceType": "ClaimResponse",
                "status": "active",
                "outcome": "complete",
                "disposition": "Claim accepted (mock)",
                "request_echo": fhir_claim,
            }
        resp = httpx.post(
            f"{self.base_url}/Claim",
            json=fhir_claim,
            headers={**self._headers(), "Content-Type": "application/fhir+json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


# --------------------------------------------------------------------------- #
# Mappers: FHIR <-> internal domain
# --------------------------------------------------------------------------- #
def fhir_class_to_internal(fhir_class_code: str) -> str:
    """Map a FHIR Encounter.class code to inpatient/outpatient."""
    return "inpatient" if fhir_class_code.upper() in {"IMP", "ACUTE", "NONAC"} else "outpatient"


def map_patient(resource: dict) -> dict:
    name = (resource.get("name") or [{}])[0]
    mrn = None
    for ident in resource.get("identifier", []):
        if "MRN" in (ident.get("system", "") + ident.get("value", "")).upper():
            mrn = ident.get("value")
            break
    if mrn is None and resource.get("identifier"):
        mrn = resource["identifier"][0].get("value")
    return {
        "epic_fhir_id": resource.get("id"),
        "mrn": mrn or f"EPIC-{resource.get('id', 'unknown')}",
        "first_name": (name.get("given") or ["Unknown"])[0],
        "last_name": name.get("family", "Unknown"),
        "birth_date": resource.get("birthDate"),
        "sex": resource.get("gender", "unknown"),
    }


def map_encounter(resource: dict) -> dict:
    fclass = (resource.get("class") or {}).get("code", "AMB")
    period = resource.get("period", {})
    reason = (resource.get("reasonCode") or [{}])[0].get("text")
    return {
        "epic_fhir_id": resource.get("id"),
        "encounter_class": fhir_class_to_internal(fclass),
        "admit_date": period.get("start", "")[:10] or None,
        "discharge_date": period.get("end", "")[:10] or None,
        "reason": reason,
    }


def map_document(resource: dict) -> dict:
    return {
        "epic_fhir_id": resource.get("id"),
        "doc_type": (resource.get("type") or {}).get("text", "Note"),
        "author": (resource.get("author") or [{}])[0].get("display"),
        # Real DocumentReference carries base64 in content[].attachment.data;
        # the mock places plain text under 'content_text' for readability.
        "text": resource.get("content_text", ""),
    }


def build_fhir_claim(
    patient: Patient, encounter: Encounter, claim: Claim
) -> dict:
    """Render a coded encounter as a FHIR R4 Claim resource for Epic."""
    diagnoses = []
    for dx in sorted(encounter.diagnoses, key=lambda d: (not d.is_principal, d.sequence)):
        system = (
            "http://hl7.org/fhir/sid/icd-10-pcs"
            if dx.system == "ICD-10-PCS"
            else FHIR_ICD10_CM
        )
        diagnoses.append(
            {
                "sequence": dx.sequence,
                "diagnosisCodeableConcept": {
                    "coding": [{"system": system, "code": dx.code, "display": dx.description}]
                },
                "type": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/ex-diagnosistype",
                                "code": "principal" if dx.is_principal else "secondary",
                            }
                        ]
                    }
                ],
            }
        )

    items = []
    for seq, line in enumerate(claim.lines, start=1):
        modifiers = [
            {"coding": [{"system": FHIR_CPT, "code": m}]}
            for m in (line.modifiers or "").split(",")
            if m.strip()
        ]
        pointers = [
            int(p) for p in (line.diagnosis_pointers or "").split(",") if p.strip().isdigit()
        ]
        items.append(
            {
                "sequence": seq,
                "diagnosisSequence": pointers,
                "productOrService": {
                    "coding": [{"system": FHIR_CPT, "code": line.code, "display": line.description}]
                },
                "modifier": modifiers,
                "quantity": {"value": line.units},
                "unitPrice": {"value": line.unit_charge, "currency": "USD"},
                "net": {"value": line.line_charge, "currency": "USD"},
            }
        )

    resource: dict[str, Any] = {
        "resourceType": "Claim",
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "institutional" if claim.claim_type == "institutional" else "professional",
                }
            ]
        },
        "use": "claim",
        "patient": {"reference": f"Patient/{patient.epic_fhir_id or patient.mrn}"},
        "created": claim.created_at.isoformat(),
        "identifier": [{"system": "urn:medicalcoding:claim", "value": claim.claim_number}],
        "diagnosis": diagnoses,
        "item": items,
        "total": {"value": claim.total_charge, "currency": "USD"},
    }
    if claim.drg_code:
        resource["supportingInfo"] = [
            {
                "sequence": 1,
                "category": {"text": "MS-DRG"},
                "code": {"coding": [{"code": claim.drg_code, "display": claim.drg_description}]},
            }
        ]
    return resource
