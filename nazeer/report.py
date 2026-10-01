"""Module 7: the evidence report (JSON; PDF export is optional).

Failures are stated plainly. Every check has a status (PASS / FAIL / INFO / NOT_RUN)
and a `blocking` flag; the verdict is FAIL if any blocking check fails. A
non-blocking FAIL (e.g. k-anonymity *before* the user applied a fix) stays
visible in the report. The report holds counts, names and metrics only, never values.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

LIMITATIONS = [
    "Detection is never 100% complete. Columns and spans the detector misses are not "
    "transformed; the human review step and the leak scan reduce but cannot remove this risk.",
    "The leak scan can only look for identifiers that were found (in columns or text). An "
    "identifier that appears only in free text and was missed there cannot be checked.",
    "A generated ID, mobile or IBAN is format-valid and may coincide with a real person's "
    "value outside this dataset.",
    "The masked twin (mode 5a) is most likely still personal data under the PDPL: each row "
    "corresponds to a real person and the key holder can re-identify by enumeration. Treat it "
    "as personal data. The synthetic twin (5b) is stronger but not proven anonymous; this "
    "report never claims anonymity.",
    "Detection scores measured on the generated demo data reflect formats we planted; they do "
    "not predict recall on real production text.",
    "SDV (and its dependencies copulas, rdt, ctgan) are BUSL-1.1: use as a Synthetic Data "
    "Service needs a commercial licence.",
]

REPORT_SCHEMA = {
    "type": "object",
    "required": ["nazeer_version", "run_id", "timestamp_utc", "mode", "input", "policy", "columns",
                 "free_text", "leak_scan", "checks", "verdict", "limitations", "outputs"],
    "properties": {
        "mode": {"enum": ["masked", "synthetic"]},
        "verdict": {"enum": ["PASS", "FAIL"]},
        "policy": {"type": "object", "required": ["source", "hash", "thresholds", "inactive_rules"]},
        "columns": {"type": "array", "items": {
            "type": "object",
            "required": ["table", "column", "tag", "kind", "confidence", "action", "human_reviewed"]}},
        "checks": {"type": "array", "minItems": 1, "items": {
            "type": "object",
            "required": ["name", "status", "blocking", "detail"],
            "properties": {"status": {"enum": ["PASS", "FAIL", "INFO", "NOT_RUN"]},
                           "blocking": {"type": "boolean"}}}},
        "leak_scan": {"type": "object", "required": ["hard_fail", "verdict", "leaked_by_kind"]},
        "limitations": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    },
}


@dataclass
class Check:
    name: str
    status: str
    blocking: bool
    detail: str
    value: object = None
    threshold: object = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ReportBuilder:
    base: dict
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, blocking: bool, detail: str, value=None, threshold=None) -> None:
        self.checks.append(Check(name, status, blocking, detail, value, threshold))

    def build(self) -> dict:
        report = dict(self.base)
        report["checks"] = [c.to_dict() for c in self.checks]
        failed = [c.name for c in self.checks if c.blocking and c.status == "FAIL"]
        report["verdict"] = "FAIL" if failed else "PASS"
        report["failed_checks"] = failed
        report["limitations"] = LIMITATIONS
        validate(report)
        return report


def validate(report: dict) -> None:
    jsonschema.validate(report, REPORT_SCHEMA)


def write_json(report: dict, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
