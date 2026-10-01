"""Independent evaluation on hand-written notes (written WITHOUT seeing the generator).

    python -m nazeer.eval_human --notes data\\human_notes.csv
    python -m nazeer.eval_human --make-ids 10      # valid fake identifiers to paste into notes

Input CSV: columns `author,note`. Every identifier is wrapped in a marker:
    ⟦ID:...⟧  ⟦MOBILE:...⟧  ⟦IBAN:...⟧  ⟦NAME:...⟧  ⟦EMAIL:...⟧
Numbers that only LOOK like identifiers (invoice / order numbers) are NOT marked.

The markers are stripped to get the clean text and the golden spans; Nazeer and the
naive baseline then run on the clean text. The output lists recall/precision per type
and every missed or extra span by type and position only, never the value.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from nazeer import detect
from nazeer import saudi_ids as s
from nazeer.evaluate import score_detection
from nazeer.models import Span
from nazeer.tableio import read_csv

MARKER = re.compile(r"⟦([A-Z_]+):(.*?)⟧", re.DOTALL)
MARKER_TYPES = {"ID": "SAUDI_ID", "MOBILE": "MOBILE", "IBAN": "IBAN", "NAME": "PERSON_NAME", "EMAIL": "EMAIL"}
TABLE, COLUMN = "human_notes", "note"


class MarkupError(ValueError):
    """A note has an unknown marker type, a nested/unclosed marker, or an empty value."""


@dataclass
class ParsedNote:
    text: str
    spans: list[tuple[int, int, str]]  # (start, end, kind) in the clean text


def parse_marked(note: str) -> ParsedNote:
    out, spans, last = [], [], 0
    pos = 0
    for m in MARKER.finditer(note):
        kind = MARKER_TYPES.get(m.group(1))
        value = m.group(2)
        if kind is None:
            raise MarkupError(f"unknown marker type {m.group(1)!r} (use {', '.join(MARKER_TYPES)})")
        if not value.strip() or "⟦" in value:
            raise MarkupError("empty or nested marker")
        chunk = note[last:m.start()]
        out.append(chunk)
        pos += len(chunk)
        spans.append((pos, pos + len(value), kind))
        out.append(value)
        pos += len(value)
        last = m.end()
    tail = note[last:]
    if "⟦" in tail or "⟧" in tail or any("⟦" in c or "⟧" in c for c in out[::2]):
        raise MarkupError("unbalanced marker bracket")
    out.append(tail)
    return ParsedNote("".join(out), spans)


def evaluate_notes(df: pd.DataFrame, ner=None) -> dict:
    texts, golden_rows, errors = [], [], []
    for row, (author, note) in enumerate(zip(df["author"].fillna(""), df["note"].fillna(""))):
        try:
            parsed = parse_marked(str(note))
        except MarkupError as e:
            errors.append({"row": row, "author": author, "error": str(e)})
            texts.append(None)
            continue
        texts.append(parsed.text)
        golden_rows += [{"table": TABLE, "row": row, "column": COLUMN, "start": a, "end": b, "type": k,
                         # names have no official format; only IDs, mobiles, IBANs and emails do
                         "valid_format": k == "PERSON_NAME" or s.is_valid(k, parsed.text[a:b])}
                        for a, b, k in parsed.spans]
    golden = pd.DataFrame(golden_rows, columns=["table", "row", "column", "start", "end", "type", "valid_format"])

    nazeer, baseline = [], []
    for row, text in enumerate(texts):
        if text is None:
            continue
        nazeer += [Span(TABLE, row, COLUMN, a, b, k, c, src) for a, b, k, c, src in detect.find_spans(text, ner)]
        baseline += [Span(TABLE, row, COLUMN, a, b, k, c, src) for a, b, k, c, src in detect.baseline_find_spans(text)]

    valid = golden[golden.valid_format] if len(golden) else golden
    result = {
        "notes": int(len(df)), "notes_with_markup_errors": errors, "authors": dict(Counter(df["author"].fillna(""))),
        "golden_by_type": dict(Counter(golden["type"])) if len(golden) else {},
        "golden_failing_official_format": dict(Counter(golden.loc[~golden.valid_format, "type"])) if len(golden) else {},
        "nazeer": score_detection(nazeer, golden),
        "baseline": score_detection(baseline, golden),
        "nazeer_on_valid_format_only": score_detection(nazeer, valid),
        "baseline_on_valid_format_only": score_detection(baseline, valid),
        "nazeer_misses": _misses(nazeer, golden),
        "nazeer_extras": _extras(nazeer, golden),
        "note": "positions index the CLEAN text (markers removed); values are never reported",
    }
    return result


def _overlap(a0, a1, b0, b1) -> bool:
    return a0 < b1 and b0 < a1


def _misses(pred: list[Span], golden: pd.DataFrame) -> list[dict]:
    out = []
    for g in golden.itertuples(index=False):
        if not any(p.row == g.row and p.type == g.type and _overlap(p.start, p.end, g.start, g.end) for p in pred):
            out.append({"row": int(g.row), "type": g.type, "start": int(g.start), "end": int(g.end),
                        "valid_format": bool(g.valid_format)})
    return out


def _extras(pred: list[Span], golden: pd.DataFrame) -> list[dict]:
    out = []
    for p in pred:
        same = golden[(golden.row == p.row) & (golden.type == p.type)] if len(golden) else golden
        if not any(_overlap(p.start, p.end, int(g.start), int(g.end)) for g in same.itertuples(index=False)):
            out.append({"row": p.row, "type": p.type, "start": p.start, "end": p.end})
    return out


def make_ids(n: int, seed: int | None = None) -> pd.DataFrame:
    """Valid, fake identifiers (correct checksums) for note writers to paste."""
    rng = random.Random(seed)
    return pd.DataFrame({
        "national_id (citizen)": [s.gen_saudi_id(rng, "1") for _ in range(n)],
        "iqama (resident)": [s.gen_saudi_id(rng, "2") for _ in range(n)],
        "mobile": [s.gen_mobile(rng) for _ in range(n)],
        "iban": [s.gen_iban(rng) for _ in range(n)],
    })


def _print(result: dict) -> None:
    print(f"notes: {result['notes']}  markup errors: {len(result['notes_with_markup_errors'])}  "
          f"golden identifiers: {sum(result['golden_by_type'].values())} {result['golden_by_type']}")
    if result["golden_failing_official_format"]:
        print(f"marked identifiers that fail the official format/checksum: {result['golden_failing_official_format']}")
    print(f"{'type':12} | {'Nazeer R':>8} {'P':>6} | {'baseline R':>10} {'P':>6} | {'Nazeer R (valid only)':>21}")
    fmt = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
    for t in ("SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"):
        n, b, v = (result[k]["per_type"][t] for k in ("nazeer", "baseline", "nazeer_on_valid_format_only"))
        if n["golden"] or n["predicted"]:
            print(f"{t:12} | {fmt(n['recall']):>8} {fmt(n['precision']):>6} | {fmt(b['recall']):>10} "
                  f"{fmt(b['precision']):>6} | {fmt(v['recall']):>21}")
    for who in ("nazeer", "baseline"):
        r = result[who]
        print(f"{who:8} overall recall={r['overall_recall']} precision={r['overall_precision']}")
    for m in result["nazeer_misses"]:
        print(f"  missed  row {m['row']:>4} {m['type']:12} chars {m['start']}-{m['end']}"
              + ("" if m["valid_format"] else "  (fails official format)"))
    for e in result["nazeer_extras"]:
        print(f"  extra   row {e['row']:>4} {e['type']:12} chars {e['start']}-{e['end']}")
    for e in result["notes_with_markup_errors"]:
        print(f"  markup error in row {e['row']} ({e['author']}): {e['error']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nazeer.eval_human", description=__doc__.splitlines()[0])
    ap.add_argument("--notes", type=Path, default=Path("data") / "human_notes.csv")
    ap.add_argument("--json", type=Path, default=Path("out") / "human_eval.json")
    ap.add_argument("--ner", choices=["gazetteer", "camel", "auto"], default="auto",
                    help="name detector (auto: CamelBERT if installed locally, else gazetteer)")
    ap.add_argument("--make-ids", type=int, metavar="N", help="print N rows of valid fake identifiers and exit")
    args = ap.parse_args(argv)
    if args.make_ids:
        print(make_ids(args.make_ids).to_csv(index=False))
        return 0
    if not args.notes.exists():
        print(f"{args.notes} not found. Copy data\\human_notes_TEMPLATE.csv and see docs\\HOW_TO_WRITE_NOTES.md",
              file=sys.stderr)
        return 1
    from nazeer.ner import get_name_detector

    ner = get_name_detector(args.ner)
    result = evaluate_notes(read_csv(args.notes), ner)
    result["name_detector"] = ner.name
    _print(result)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
