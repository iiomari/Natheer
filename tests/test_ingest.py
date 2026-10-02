"""Messy real-world files must load and run end to end (detection + masked twin) without setup."""
import io
import random

import pytest
from openpyxl import Workbook

from nazeer import pipeline
from nazeer import saudi_ids as s
from nazeer.ingest import LIMITS, IngestError, read_files
from nazeer.policy import load_policy

KEY = b"ingest-test-key-0123456789-0123456789"
rng = random.Random(7)
CITIES = ["الرياض", "جدة", "الدمام", "مكة المكرمة", "أبها"]


def _people(n=60):
    out = []
    for i in range(n):
        g = rng.choice("MF")
        out.append({
            "name": f"{s.gen_first_name(rng, g)} {s.gen_family_name(rng)}",
            "nid": s.gen_saudi_id(rng),
            "mobile": s.gen_mobile(rng),
            "iban": s.gen_iban(rng),
            "city": rng.choice(CITIES),
            "age": str(rng.randint(20, 70)),
        })
    return out


def _arabic_digits(x: str) -> str:
    return x.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


@pytest.fixture(scope="module")
def samples() -> dict[str, list[tuple[str, bytes]]]:
    p = _people()
    files = {}

    # 1. Windows-1256, semicolons, Arabic headers, an Arabic note with a spaced mobile
    #    (Windows-1256 has no Arabic-Indic digits, so such files carry ASCII digits)
    lines = ["الاسم;رقم الهوية;الجوال;المدينة;ملاحظات"]
    for r in p:
        note = f"تواصل مع العميل على {r['mobile'][:3]} {r['mobile'][3:6]} {r['mobile'][6:]} للمتابعة"
        lines.append(f"{r['name']};{r['nid']};{r['mobile']};{r['city']};{note}")
    files["cp1256_semicolon"] = [("عملاء.csv", "\r\n".join(lines).encode("cp1256"))]

    # 2. UTF-8 with BOM, tab separated, NO header row
    lines = ["\t".join([r["nid"], r["name"], r["city"], r["age"]]) for r in p]
    files["bom_tab_noheader"] = [("export.tsv", "﻿".encode() + "\n".join(lines).encode("utf-8"))]

    # 3. Excel: two related sheets, an empty sheet, trailing empty columns, numbers and dates
    wb = Workbook()
    ws = wb.active
    ws.title = "العملاء"
    ws.append(["customer_id", "الاسم", "الهوية", "IBAN", None, None])
    for i, r in enumerate(p, 1):
        ws.append([1000 + i, r["name"], int(r["nid"]), r["iban"], None, None])
    wo = wb.create_sheet("orders")
    wo.append(["order_id", "customer_id", "amount", "order_date"])
    from datetime import datetime
    for j in range(150):
        wo.append([5000 + j, 1000 + rng.randint(1, len(p)), round(rng.uniform(10, 900), 2), datetime(2025, 1 + j % 12, 1 + j % 27)])
    wb.create_sheet("فارغة")
    buf = io.BytesIO()
    wb.save(buf)
    files["excel_multisheet"] = [("data.xlsx", buf.getvalue())]

    # 4. UTF-8, duplicate headers, an empty column, blank lines, quoted commas, mixed types, missing cells
    lines = ['name,name,empty,value,comment']
    for i, r in enumerate(p):
        val = rng.choice([str(i), f"{i}.5", "N/A", "", "abc"])
        lines.append(f'{r["name"]},{r["city"]},,{val},"يقول: مرحبا, شكرا"')
        if i % 10 == 0:
            lines.append(",,,,")
            lines.append("")
    files["utf8_duplicates_empty"] = [("messy.csv", "\n".join(lines).encode("utf-8"))]

    # 5. two related files with unknown English headers (no hint words)
    cust = ["cid,nm,ph,ct"] + [f"{700 + i},{r['name']},{r['mobile']},{r['city']}" for i, r in enumerate(p)]
    tx = ["tid,cref,amt"] + [f"{9000 + j},{700 + rng.randrange(len(p))},{rng.randint(5, 999)}" for j in range(200)]
    files["two_related_files"] = [("cust.csv", "\n".join(cust).encode()), ("tx.csv", "\n".join(tx).encode())]

    # 6. UTF-16 tab separated (Excel "Unicode Text")
    lines = ["الاسم\tالجوال\tالعمر"] + [f"{r['name']}\t{r['mobile']}\t{r['age']}" for r in p]
    files["utf16_unicode_text"] = [("unicode.txt", "\n".join(lines).encode("utf-16"))]

    # 7. a single unrelated table with no identifiers at all
    lines = ["category,score"] + [f"{rng.choice('ABC')},{rng.randint(1, 5)}" for _ in range(80)]
    files["no_identifiers"] = [("survey.csv", "\n".join(lines).encode())]
    return files


def test_each_messy_file_loads(samples):
    expected = {
        "cp1256_semicolon": ("windows-1256", ";", "detected"),
        "bom_tab_noheader": ("utf-8-sig", "tab", "generated"),
        "utf16_unicode_text": ("utf-16", "tab", "detected"),
    }
    for name, files in samples.items():
        res = read_files(files)
        assert res.tables, name
        for df in res.tables.values():
            assert len(df) > 0 and df.shape[1] > 0
        if name in expected:
            n = res.notes[0]
            assert (n.encoding, n.delimiter, n.header) == expected[name], name
    excel = read_files(samples["excel_multisheet"])
    assert set(excel.tables) == {"العملاء", "orders"}  # the empty sheet is skipped
    assert list(excel.tables["العملاء"].columns) == ["customer_id", "الاسم", "الهوية", "IBAN"]
    assert excel.tables["orders"]["order_date"].iloc[0] == "2025-01-01"
    assert excel.tables["العملاء"]["customer_id"].iloc[0] == "1001"  # not "1001.0"
    messy = read_files(samples["utf8_duplicates_empty"])
    df = next(iter(messy.tables.values()))
    assert list(df.columns) == ["name", "name_2", "value", "comment"]  # empty column dropped
    assert messy.notes[0].dropped_empty_columns == 1 and messy.notes[0].dropped_empty_rows >= 6
    assert df["comment"].iloc[0] == "يقول: مرحبا, شكرا"


@pytest.mark.parametrize("name", ["cp1256_semicolon", "bom_tab_noheader", "excel_multisheet", "utf8_duplicates_empty",
                                  "two_related_files", "utf16_unicode_text", "no_identifiers"])
def test_masked_twin_always_works(samples, name):
    tables = read_files(samples[name]).tables
    an = pipeline.analyze(tables, name)
    res = pipeline.run_masked(an, load_policy(pipeline.DEFAULT_POLICY), KEY)
    assert res.report["leak_scan"]["verdict"] == "PASS", name
    assert not res.twin_withheld
    assert {t: len(d) for t, d in res.twin.items()} == {t: len(d) for t, d in tables.items()}


def test_identifiers_found_in_messy_files(samples):
    an = pipeline.analyze(read_files(samples["cp1256_semicolon"]).tables, "x")
    kinds = {d.kind for d in an.detections if d.tag == "DIRECT_ID"}
    assert {"SAUDI_ID", "MOBILE", "PERSON_NAME"} <= kinds
    assert any(sp.type == "MOBILE" for sp in an.spans)  # spaced Arabic-digit mobile inside the note
    an = pipeline.analyze(read_files(samples["bom_tab_noheader"]).tables, "x")
    assert any(d.kind == "SAUDI_ID" and d.tag == "DIRECT_ID" for d in an.detections)  # no header, still found


def test_relationships_detected_when_possible_else_independent(samples):
    # Unrelated-looking names (cref vs cid): no relationship is claimed; both tables work alone.
    an = pipeline.analyze(read_files(samples["two_related_files"]).tables, "x")
    assert an.profile.foreign_keys == []
    # The same data with a reference name resembling the key: the relationship is found.
    (c_name, cust), (t_name, tx) = samples["two_related_files"]
    tx = tx.replace(b"tid,cref,amt", b"tid,cust_id,amt")
    an = pipeline.analyze(read_files([(c_name, cust), (t_name, tx)]).tables, "x")
    fks = {(f.child_table, f.child_column, f.parent_table, f.parent_column) for f in an.profile.foreign_keys}
    assert ("tx", "cust_id", "cust", "cid") in fks
    an = pipeline.analyze(read_files(samples["excel_multisheet"]).tables, "x")
    assert any(f.child_table == "orders" and f.parent_table == "العملاء" for f in an.profile.foreign_keys)


def test_synthetic_runs_without_a_target(samples):
    an = pipeline.analyze(read_files(samples["excel_multisheet"]).tables, "x")
    res = pipeline.run_synthetic(an, load_policy(pipeline.DEFAULT_POLICY))
    assert res.report["utility"].get("note") and res.report["leak_scan"]["verdict"] == "PASS"


@pytest.mark.parametrize("files,code", [
    ([("old.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)], "old_excel"),
    ([("doc.pdf", b"%PDF-1.4 ...")], "unsupported_type"),
    ([("empty.csv", b"   \n\n")], "empty_file"),
    ([("bin.csv", b"\x00\x01\x02\xff\xfe\x00" * 50)], "binary_file"),
    ([("broken.xlsx", b"PK\x03\x04 not really a zip")], "bad_excel"),
    ([("big.csv", b"a\n" + b"1\n" * (LIMITS["max_file_bytes"] // 2 + 1))], "file_too_large"),
    ([], "no_files"),
])
def test_clear_errors(files, code):
    with pytest.raises(IngestError) as e:
        read_files(files)
    assert e.value.code == code
