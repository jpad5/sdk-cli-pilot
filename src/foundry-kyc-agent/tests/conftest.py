from __future__ import annotations

from dataclasses import replace

import pytest

from kyc_core.config import settings


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("KYC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DEMO_MODE", "mock")
    settings.cache_clear()
    yield replace(settings(), data_dir=tmp_path, demo_mode="mock", sar_auto_approve=False)
    settings.cache_clear()
