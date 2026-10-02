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
    "Nazeer replaces direct identifiers. It does not measure the risk of recognising people from a "
    "combination of the remaining columns (such as age, city and diagnosis) in the masked twin. For "
    "data that needs that protection, use the synthetic twin.",
    "Detection is never 100% complete. Columns and spans the detector misses are not "
    "transformed; the human review step and the leak scan reduce but cannot remove this risk.",
    "The leak scan looks for every identifier that was found, and the residual scan flags any valid "
    "national ID, mobile or IBAN left in the twin that Nazeer did not generate. An identifier in a "
    "format no validator recognises (for example a name the detector missed) cannot be caught.",
    "Values the detector was unsure of are left unchanged for human review unless an admin approves "
    "replacing them.",
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

LIMITATIONS_AR = [
    "نَظير يستبدل المعرّفات المباشرة، ولا يقيس خطر التعرّف على الأشخاص عبر تركيب الأعمدة المتبقية (مثل العمر "
    "والمدينة والتشخيص) في النظير المُقنَّع. للبيانات التي تحتاج هذه الحماية، يُستخدم النظير الاصطناعي.",
    "الكشف لا يكتمل بنسبة 100%: ما لا يكتشفه نَظير لا يُستبدل. المراجعة البشرية وفحص التسريب يقلّلان هذا الخطر "
    "ولا يلغيانه.",
    "يبحث فحص التسريب عن كل معرّف اكتُشف، ويرصد فحص البقايا أي رقم هوية أو جوال أو آيبان صالح بقي في النظير "
    "دون أن يولّده نَظير. أما معرّف بصيغة لا يتعرّف عليها أي مدقّق (مثل اسم فات الكاشف) فلا يمكن رصده.",
    "القيم التي لم يتأكد منها الكاشف تُترك كما هي للمراجعة البشرية، ما لم يوافق المدير على استبدالها.",
    "الرقم البديل (هوية أو جوال أو آيبان) صحيح الصيغة وقد يطابق صدفةً رقم شخص حقيقي خارج هذه البيانات.",
    "النظير المقنّع غالباً ما يزال بيانات شخصية وفق نظام حماية البيانات الشخصية: كل صف يقابل شخصاً حقيقياً، "
    "وحامل المفتاح يستطيع إعادة التعرّف. عامِله معاملة البيانات الشخصية. النظير الاصطناعي أقوى لكنه غير مثبت "
    "أنه مجهول الهوية، والتقرير لا يدّعي ذلك أبداً.",
    "دقة الكشف المقيسة على بيانات العرض المولَّدة تعكس الصيغ التي زرعناها، ولا تتنبأ بالدقة على نصوص حقيقية.",
    "مكتبة SDV واعتمادياتها بترخيص BUSL-1.1: تقديمها خدمةً لتوليد البيانات يحتاج ترخيصاً تجارياً.",
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
        report["limitations_ar"] = LIMITATIONS_AR
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
