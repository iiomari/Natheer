"""Audit trail: who, what, when. Never values.

meta may hold only short codes, counts and booleans. Any string that looks like a value
(email, long digit run, IBAN) is replaced, so a mistake at a call site cannot leak data.
"""
from __future__ import annotations

from sqlalchemy.orm import Session as DbSession

from nazeer.safe_log import REDACTED, redact
from nazeer_api.models import AuditEvent

MAX_META_STR = 64


def _clean(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    if len(text) > MAX_META_STR or redact(text) != text:
        return REDACTED
    return text


def record(db: DbSession, action: str, *, org_id: str | None = None, actor_user_id: str | None = None,
           target_type: str | None = None, target_id: str | None = None, **meta) -> AuditEvent:
    event = AuditEvent(org_id=org_id, actor_user_id=actor_user_id, action=action, target_type=target_type,
                       target_id=target_id, meta={k: _clean(v) for k, v in meta.items()})
    db.add(event)
    return event
