"""CPT / HCPCS lookup and format helpers.

CPT structure recognised here:
  * Category I  -> 5 numeric digits           (e.g. 99213)
  * Category II -> 4 digits followed by 'F'    (e.g. 3074F) performance measures
  * Category III-> 4 digits followed by 'T'    (e.g. 0042T) emerging technology
  * HCPCS L2    -> 1 letter followed by 4 digits (e.g. J1100)
"""
from __future__ import annotations

import re

from app.coding import codesets

CAT_I = re.compile(r"^\d{5}$")
CAT_II = re.compile(r"^\d{4}F$", re.I)
CAT_III = re.compile(r"^\d{4}T$", re.I)
HCPCS = re.compile(r"^[A-CEGHJ-MP-V]\d{4}$", re.I)
# A standalone CPT modifier is two chars: digits (e.g. 25, 59) or letters
# (e.g. TC, AS) or the Category II ones like 1P.
MODIFIER = re.compile(r"^[0-9A-Z]{2}$", re.I)


def classify_format(code: str) -> str | None:
    """Return the CPT/HCPCS category for a code, or None if it is malformed."""
    code = code.strip().upper()
    if CAT_I.match(code):
        return "I"
    if CAT_II.match(code):
        return "II"
    if CAT_III.match(code):
        return "III"
    if HCPCS.match(code):
        return "HCPCS"
    return None


def is_valid_format(code: str) -> bool:
    return classify_format(code) is not None


def is_valid_modifier_format(modifier: str) -> bool:
    return bool(MODIFIER.match(modifier.strip()))


def lookup(code: str) -> dict | None:
    return codesets.cpt_index().get(code.strip().upper())


def search(term: str, limit: int = 25) -> list[dict]:
    term = term.strip().lower()
    out: list[dict] = []
    for code, row in codesets.cpt_index().items():
        if term in code.lower() or term in row["short"].lower():
            out.append(row)
        if len(out) >= limit:
            break
    return out
