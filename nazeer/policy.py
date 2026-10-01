"""Module 3: policy engine. Turns detections + YAML policy + human overrides into
one Decision per column. Overrides always win and are recorded."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from nazeer.models import ColumnDetection, DatasetProfile

log = logging.getLogger(__name__)

ACTIONS = {"keep", "pseudonymize", "generalize", "replace_spans", "remap", "drop"}
KIND_KEYS = {"SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"}
SPECIAL_KEYS = {"free_text", "primary_key", "default"}
DEFAULT_THRESHOLDS = {"k_anonymity_min": 5, "max_utility_drop": 0.05, "min_span_confidence": 0.5}


@dataclass
class Policy:
    rules: dict[str, dict]
    thresholds: dict[str, float]
    source: str = "<dict>"

    @property
    def hash(self) -> str:
        blob = json.dumps({"rules": self.rules, "thresholds": self.thresholds}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class Decision:
    table: str
    column: str
    action: str
    params: dict = field(default_factory=dict)
    rule: str = ""            # which policy key (or "override") produced the action
    tag: str = "NORMAL"
    kind: str | None = None
    human_override: bool = False
    remap_group: str | None = None  # PK and its FKs share one pseudonym space


def load_policy(path: Path) -> Policy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return policy_from_dict(data, source=str(path))


def policy_from_dict(data: dict, source: str = "<dict>") -> Policy:
    rules = {str(k): dict(v or {}) for k, v in (data.get("policy") or {}).items()}
    for key, rule in rules.items():
        if rule.get("action") not in ACTIONS:
            raise ValueError(f"policy rule {key!r}: unknown action {rule.get('action')!r}")
    thresholds = {**DEFAULT_THRESHOLDS, **(data.get("thresholds") or {})}
    return Policy(rules=rules, thresholds=thresholds, source=source)


def apply_overrides(detections: list[ColumnDetection], overrides: dict[str, dict]) -> list[ColumnDetection]:
    """`overrides` maps "table.column" -> {"tag": ..., "kind": ..., "action": {...}} (all optional)."""
    out = []
    for d in detections:
        o = overrides.get(f"{d.table}.{d.column}")
        if not o:
            out.append(d)
            continue
        out.append(replace(d, tag=o.get("tag", d.tag),
                           kind=o.get("kind", d.kind if o.get("tag", d.tag) == "DIRECT_ID" else None),
                           needs_review=False, human_override=True, reason="human override"))
    return out


def resolve(policy: Policy, prof: DatasetProfile, detections: list[ColumnDetection],
            overrides: dict[str, dict] | None = None) -> list[Decision]:
    overrides = overrides or {}
    detections = apply_overrides(detections, overrides)
    pk_group = {(t.name, t.primary_key): f"PK:{t.name}.{t.primary_key}" for t in prof.tables.values() if t.primary_key}
    for fk in prof.foreign_keys:
        pk_group[(fk.child_table, fk.child_column)] = f"PK:{fk.parent_table}.{fk.parent_column}"

    decisions = []
    for d in detections:
        key = f"{d.table}.{d.column}"
        group = pk_group.get((d.table, d.column))
        explicit = (overrides.get(key) or {}).get("action")
        if explicit:
            rule, name = dict(explicit), "override"
        elif d.tag == "DIRECT_ID" and d.kind in policy.rules:
            rule, name = policy.rules[d.kind], d.kind
        elif group and "primary_key" in policy.rules:
            rule, name = policy.rules["primary_key"], "primary_key"
        elif d.column.lower() in policy.rules:
            rule, name = policy.rules[d.column.lower()], d.column.lower()
        elif d.tag == "FREE_TEXT" and "free_text" in policy.rules:
            rule, name = policy.rules["free_text"], "free_text"
        else:
            rule, name = policy.rules.get("default", {"action": "keep"}), "default"
        if rule["action"] not in ACTIONS:
            raise ValueError(f"{key}: unknown action {rule['action']!r}")
        params = {k: v for k, v in rule.items() if k != "action"}
        decisions.append(Decision(d.table, d.column, rule["action"], params, name, d.tag, d.kind,
                                  d.human_override, group if rule["action"] == "remap" else None))

    used = {dec.rule for dec in decisions}
    inactive = [k for k in policy.rules if k not in used and k not in SPECIAL_KEYS | KIND_KEYS]
    log.info("policy resolved %d columns; %d overrides; %d inactive rules",
             len(decisions), sum(dec.human_override for dec in decisions), len(inactive))
    return decisions


def inactive_rules(policy: Policy, decisions: list[Decision]) -> list[str]:
    used = {d.rule for d in decisions}
    return sorted(k for k in policy.rules if k not in used and k not in SPECIAL_KEYS | KIND_KEYS)
