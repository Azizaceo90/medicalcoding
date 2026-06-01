"""Tests for charge calculation and MS-DRG assignment."""
from app.billing.claims import assign_drg


def test_drg_assignment_by_principal_dx():
    drg = assign_drg("K35.80", {"K35.80"}, set())
    assert drg is not None
    assert drg["drg"] == "338"
    assert drg["payment"] > 0


def test_drg_assignment_by_pcs():
    drg = assign_drg(None, set(), {"0SR9019"})
    assert drg is not None
    assert drg["drg"] == "470"


def test_no_drg_for_unknown():
    assert assign_drg("Z00.00", {"Z00.00"}, set()) is None
