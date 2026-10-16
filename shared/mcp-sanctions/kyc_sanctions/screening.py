from __future__ import annotations

import csv
import unicodedata

from kyc_core.config import settings
from kyc_core.models import ScreeningHit, ScreeningResult
from rapidfuzz.fuzz import token_sort_ratio


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in decomposed
            if not unicodedata.combining(character)
        ).split()
    )


def _rows() -> list[dict[str, str]]:
    with (settings().mock_dir / "sanctions.csv").open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def list_sources() -> list[str]:
    return sorted({row["list"] for row in _rows()})


def screen(name: str, dob: str | None = None, country: str | None = None) -> ScreeningResult:
    """Screen local fixtures; one best match per row, with mismatch penalties."""
    rows = _rows()
    query = normalize(name)
    hits = []
    for row in rows:
        canonical = normalize(row["name"])
        aliases = [normalize(alias) for alias in row["aliases"].split(";") if normalize(alias)]
        if not query:
            continue
        if query == canonical:
            score, match_type = 1.0, "exact"
        elif query in aliases:
            score, match_type = 0.95, "alias"
        else:
            score = max(token_sort_ratio(query, candidate) / 100 for candidate in [canonical, *aliases])
            if score < 0.80:
                continue
            match_type = "fuzzy"
        if dob and row["dob"] and dob.strip() != row["dob"].strip():
            score -= 0.1
        if country and row["country"] and normalize(country) != normalize(row["country"]):
            score -= 0.1
        score = round(score, 6)
        if match_type == "fuzzy" and score < 0.80:
            continue
        hits.append(ScreeningHit(
            matched_name=row["name"], list_name=row["list"], match_type=match_type,
            score=score, hit_type=row["type"], country=row["country"] or None,
        ))
    return ScreeningResult(
        query_name=name, hits=sorted(hits, key=lambda hit: (-hit.score, hit.list_name, hit.matched_name)),
        sources_checked=sorted({row["list"] for row in rows}),
    )
