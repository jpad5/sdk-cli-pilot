from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from kyc_core.config import settings
from kyc_core.models import CustomerProfile, ScreeningResult

from kyc_sanctions import list_sources, lookup_customer, screen
from kyc_sanctions.server import mcp

MOCK_DIR = Path(__file__).resolve().parents[2] / "mock"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("KYC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KYC_MOCK_DIR", str(MOCK_DIR))
    monkeypatch.setenv("DEMO_MODE", "mock")
    settings.cache_clear()
    yield
    settings.cache_clear()


def test_all_fixtures_validate():
    profiles = [CustomerProfile.model_validate(record) for record in json.loads((MOCK_DIR / "customers.json").read_text())]
    assert len(profiles) == 8
    assert len({profile.customer_id for profile in profiles}) == 8
    templates = json.loads((MOCK_DIR / "llm_responses.json").read_text())
    assert set(templates) == {"approve", "enhanced_due_diligence", "escalate_sar", "reject", "unknown"}
    for template in templates.values():
        assert template.format(customer_name="Synthetic Customer")


def test_exact_and_normalized_match():
    result = screen("  ZÓRAVIAN, Umbra-Trading!  ")
    assert result.hits[0].match_type == "exact"
    assert result.hits[0].score == 1.0
    assert result.has_sanction_hit
    assert result.sources_checked == list_sources()
    assert len(result.sources_checked) == 4


def test_alias():
    result = screen("nightglass exports", country="kp")
    assert result.hits[0].matched_name == "Obsidian Moon Freighters"
    assert result.hits[0].match_type == "alias"
    assert result.hits[0].score == 0.95
    assert result.has_sanction_hit


@pytest.mark.parametrize("name", ["Zoravian Umbra Tradng", "Nightglass Exprts"])
def test_fuzzy(name):
    result = screen(name)
    assert result.hits
    assert result.hits[0].match_type == "fuzzy"
    assert 0.80 <= result.hits[0].score < 1.0


@pytest.mark.parametrize("name", ["Liora Fablebrook", "Quillhaven Robotics", "Unlisted Xylophone Warehouse", "", "!!!"])
def test_no_hit_and_near_miss(name):
    result = screen(name)
    assert result.hits == []
    assert not result.has_sanction_hit
    assert len(result.sources_checked) == 4


@pytest.mark.parametrize("dob,country,score", [
    ("1968-03-14", "RU", 1.0),
    ("1968-03-15", "RU", 0.9),
    ("1968-03-14", "US", 0.9),
    ("1968-03-15", "US", 0.8),
    (None, None, 1.0),
])
def test_dob_country_mismatch(dob, country, score):
    result = screen("Dravik Cinderwhorl", dob=dob, country=country)
    assert result.hits[0].score == score
    assert result.has_sanction_hit == (score >= 0.85)


def test_fuzzy_below_cutoff_after_penalties():
    result = screen("Dravik Cinderwhorlx", dob="1900-01-01", country="US")
    assert not result.hits


def test_missing_reference_dob_does_not_penalize():
    assert screen("Zoravian Umbra Trading", dob="1900-01-01").hits[0].score == 1.0


def test_pep_and_adverse_media():
    assert screen("Orven Glimmerquay").has_pep_hit
    result = screen("Vesper Tanglewick")
    assert result.hits[0].hit_type == "adverse_media"
    assert not result.has_sanction_hit


@pytest.mark.parametrize("query", ["cust-1001", " LIORA FABLEBROOK "])
def test_lookup(query):
    profile = lookup_customer(query)
    assert isinstance(profile, CustomerProfile)
    assert profile.customer_id == "CUST-1001"


def test_lookup_unknown():
    assert lookup_customer("CUST-9999") is None


def test_screening_does_not_write_audit(tmp_path):
    screen("Zoravian Umbra Trading")
    lookup_customer("CUST-1001")
    list_sources()
    assert not (tmp_path / "audit.jsonl").exists()


def _decode(result):
    if isinstance(result, tuple):
        result = result[1]
    if isinstance(result, dict):
        return result.get("result", result)
    if not result:
        return None
    values = [json.loads(block.text) for block in result]
    return values[0] if len(values) == 1 else values


def test_mcp_in_process_and_audit(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from kyc_sanctions import server

    spans = []

    @contextmanager
    def recorded_span(name, **attrs):
        spans.append((name, attrs))
        yield

    monkeypatch.setattr(server, "span", recorded_span)

    async def invoke():
        tools = await mcp.list_tools()
        assert {tool.name for tool in tools} == {"screen_name", "lookup_customer", "list_sources"}
        screened = _decode(await mcp.call_tool("screen_name", {"name": "Zoravian Umbra Trading"}))
        assert ScreeningResult.model_validate(screened).has_sanction_hit
        customer = _decode(await mcp.call_tool("lookup_customer", {"customer_id_or_name": "CUST-1001"}))
        assert customer["customer_id"] == "CUST-1001"
        assert _decode(await mcp.call_tool("lookup_customer", {"customer_id_or_name": "missing"})) is None
        sources = _decode(await mcp.call_tool("list_sources", {}))
        assert sources == list_sources()

    asyncio.run(invoke())
    events = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [event["tool"] for event in events] == ["screen_name", "lookup_customer", "lookup_customer", "list_sources"]
    assert all(event["event"] == "mcp_tool_call" and "args" in event for event in events)
    assert [attrs["tool"] for _, attrs in spans] == [event["tool"] for event in events]


def test_failed_tool_call_is_audited(tmp_path, monkeypatch):
    monkeypatch.setenv("KYC_MOCK_DIR", str(tmp_path / "missing"))
    settings.cache_clear()
    with pytest.raises(Exception, match="Error executing tool"):
        asyncio.run(mcp.call_tool("screen_name", {"name": "Synthetic Example"}))
    event = json.loads((tmp_path / "audit.jsonl").read_text())
    assert event["event"] == "mcp_tool_call"
    assert event["tool"] == "screen_name"

