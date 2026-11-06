import sys

import pytest
from fastapi import HTTPException

from dependencies.auth import _enforce_dev_only_account


def test_devadmin_rejected_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(HTTPException) as exc:
        _enforce_dev_only_account({"username": "devadmin"})
    assert exc.value.status_code == 401


def test_devadmin_allowed_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    _enforce_dev_only_account({"username": "devadmin"})  # no raise


def test_other_user_allowed_even_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    _enforce_dev_only_account({"username": "superadmin"})  # no raise
