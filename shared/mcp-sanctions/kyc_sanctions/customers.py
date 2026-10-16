from __future__ import annotations

import json

from kyc_core.config import settings
from kyc_core.models import CustomerProfile


def lookup_customer(customer_id_or_name: str) -> CustomerProfile | None:
    query = customer_id_or_name.strip().casefold()
    records = json.loads((settings().mock_dir / "customers.json").read_text(encoding="utf-8-sig"))
    for record in records:
        profile = CustomerProfile.model_validate(record)
        if query in (profile.customer_id.casefold(), profile.full_name.casefold()):
            return profile
    return None
