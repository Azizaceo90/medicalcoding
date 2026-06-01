"""Loads the ICD / CPT / edit reference data once and indexes it for lookup.

In production these tables would live in a database or a licensed terminology
service (and CPT would require an AMA license). For this system they are loaded
from JSON under ``data/`` and cached in module-level dictionaries.
"""
from __future__ import annotations

import json
from functools import lru_cache

from app.config import DATA_DIR


@lru_cache(maxsize=1)
def _raw_icd() -> dict:
    with open(DATA_DIR / "icd10.json", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _raw_cpt() -> dict:
    with open(DATA_DIR / "cpt.json", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _raw_edits() -> dict:
    with open(DATA_DIR / "edits.json", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def icd_cm_index() -> dict[str, dict]:
    return {row["code"]: row for row in _raw_icd()["cm"]}


@lru_cache(maxsize=1)
def icd_pcs_index() -> dict[str, dict]:
    return {row["code"]: row for row in _raw_icd()["pcs"]}


@lru_cache(maxsize=1)
def cpt_index() -> dict[str, dict]:
    return {row["code"]: row for row in _raw_cpt()["codes"]}


@lru_cache(maxsize=1)
def ncci_index() -> dict[tuple[str, str], dict]:
    """Index NCCI PTP edits by (column1, column2) code pair."""
    return {
        (row["column1"], row["column2"]): row
        for row in _raw_edits()["ncci_ptp"]
    }


@lru_cache(maxsize=1)
def medical_necessity_index() -> dict[str, set[str]]:
    return {
        row["cpt"]: set(row["supporting_icd"])
        for row in _raw_edits()["medical_necessity"]
    }
