"""Application configuration.

Values are read from environment variables so the same image can run against a
local SQLite database in development and a managed Postgres / Epic sandbox in
production without code changes.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings:
    """Runtime settings sourced from the environment."""

    APP_NAME: str = os.getenv("APP_NAME", "Medical Coding & Billing System")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'medicalcoding.db'}"
    )

    # Epic on FHIR (R4) connection details. Defaults point at Epic's public
    # sandbox so the integration can be exercised end-to-end out of the box.
    # See https://fhir.epic.com/ for registration and the sandbox base URL.
    EPIC_FHIR_BASE_URL: str = os.getenv(
        "EPIC_FHIR_BASE_URL",
        "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
    )
    EPIC_CLIENT_ID: str = os.getenv("EPIC_CLIENT_ID", "")
    EPIC_CLIENT_SECRET: str = os.getenv("EPIC_CLIENT_SECRET", "")
    EPIC_TOKEN_URL: str = os.getenv(
        "EPIC_TOKEN_URL",
        "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token",
    )
    # When true, the Epic client never makes network calls and returns
    # deterministic sample resources instead. Keeps demos/tests offline-safe.
    EPIC_MOCK_MODE: bool = os.getenv("EPIC_MOCK_MODE", "true").lower() == "true"

    # Illustrative conversion factor used to turn work RVUs into a charge when a
    # fee-schedule rate is not present for a code.
    MEDICARE_CONVERSION_FACTOR: float = float(
        os.getenv("MEDICARE_CONVERSION_FACTOR", "32.74")
    )


settings = Settings()
