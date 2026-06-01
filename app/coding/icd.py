"""ICD-10 lookup helpers (ICD-10-CM diagnoses and ICD-10-PCS procedures)."""
from __future__ import annotations

import re

from app.coding import codesets

# ICD-10-CM: a letter, two alphanumerics, optional dot + up to 4 more chars.
CM_PATTERN = re.compile(r"^[A-TV-Z][0-9][0-9AB](\.[0-9A-TV-Z]{1,4})?$", re.I)
# ICD-10-PCS: exactly 7 alphanumeric characters (no I or O).
PCS_PATTERN = re.compile(r"^[0-9A-HJ-NP-Z]{7}$", re.I)


def is_valid_cm_format(code: str) -> bool:
    return bool(CM_PATTERN.match(code.strip()))


def is_valid_pcs_format(code: str) -> bool:
    return bool(PCS_PATTERN.match(code.strip()))


def lookup_cm(code: str) -> dict | None:
    return codesets.icd_cm_index().get(code.strip().upper())


def lookup_pcs(code: str) -> dict | None:
    return codesets.icd_pcs_index().get(code.strip().upper())


def search(term: str, limit: int = 25) -> list[dict]:
    """Case-insensitive search across CM + PCS by code prefix or description."""
    term = term.strip().lower()
    results: list[dict] = []
    for system, index in (
        ("ICD-10-CM", codesets.icd_cm_index()),
        ("ICD-10-PCS", codesets.icd_pcs_index()),
    ):
        for code, row in index.items():
            if term in code.lower() or term in row["description"].lower():
                results.append({"system": system, **row})
            if len(results) >= limit:
                return results
    return results
