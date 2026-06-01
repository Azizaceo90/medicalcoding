"""Shared pytest fixtures.

A throwaway SQLite database is configured *before* the app is imported so the
engine binds to it. Epic stays in mock mode so tests never touch the network.
"""
import os
import tempfile

import pytest

# Must be set before any `app.*` import so config picks it up.
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["EPIC_MOCK_MODE"] = "true"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.database import init_db
    from app.main import app

    init_db()
    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session, exitstatus):
    os.close(_DB_FD)
    try:
        os.remove(_DB_PATH)
    except OSError:
        pass
