from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings, settings
from .models import SarDraft


class ToolNotAllowedError(PermissionError):
    pass


class ToolPolicy:
    """Allow-list enforcement for agent tool calls."""

    def __init__(self, allowed: tuple[str, ...] | None = None, cfg: Settings | None = None):
        self.cfg = cfg or settings()
        self.allowed = set(allowed if allowed is not None else self.cfg.allowed_tools)

    def check(self, tool_name: str) -> None:
        if tool_name not in self.allowed:
            AuditLog(cfg=self.cfg).write("tool_blocked", tool=tool_name)
            raise ToolNotAllowedError(f"Tool '{tool_name}' is not in the governance allow-list")


class AuditLog:
    """Append-only JSONL audit trail (one record per governed action)."""

    _lock = threading.Lock()

    def __init__(self, path: Path | None = None, cfg: Settings | None = None):
        cfg = cfg or settings()
        self.path = path or cfg.data_dir / "audit.jsonl"

    def write(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return record

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


def require_approval(sar: SarDraft, approver: str | None = None, cfg: Settings | None = None) -> SarDraft:
    """Human-in-the-loop gate: a SAR is never filed without a named approver."""
    cfg = cfg or settings()
    audit = AuditLog(cfg=cfg)
    if approver:
        sar = sar.model_copy(update={"status": "approved", "approved_by": approver})
        audit.write("sar_approved", sar_id=sar.sar_id, customer_id=sar.customer_id, approver=approver)
    elif cfg.sar_auto_approve:
        sar = sar.model_copy(update={"status": "approved", "approved_by": "auto-policy"})
        audit.write("sar_auto_approved", sar_id=sar.sar_id, customer_id=sar.customer_id)
    else:
        sar = sar.model_copy(update={"status": "pending_approval"})
        audit.write("sar_pending_approval", sar_id=sar.sar_id, customer_id=sar.customer_id)
    return sar
