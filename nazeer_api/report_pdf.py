"""One-page Arabic PDF of a twin report (the same content as the report page, no technical terms).

fpdf2 with HarfBuzz text shaping (uharfbuzz): Arabic letters are joined and laid out right to left
exactly as in a browser. Fonts: IBM Plex Sans Arabic (SIL OFL, bundled in assets/fonts).
Counts and names only, never a data value.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

RIYADH = timezone(timedelta(hours=3))  # no daylight saving in Saudi Arabia
from pathlib import Path

FONTS = Path(__file__).parent / "assets" / "fonts"
KIND_AR = {"SAUDI_ID": "هوية / إقامة", "MOBILE": "جوال", "IBAN": "آيبان", "EMAIL": "بريد إلكتروني",
           "PERSON_NAME": "اسم"}
RULE_AR = {"trim": "المسافات والمحارف الخفية", "nulls": "القيم الفارغة", "numbers": "أرقام مخزّنة كنص",
           "dates": "توحيد التواريخ", "dedupe": "الصفوف المكررة", "arabic": "توحيد الحروف العربية",
           "phones": "توحيد صيغة الجوال", "merges": "دمج تهجئات الفئات"}
GREEN, RED, AMBER, INK, MUTED, LINE = (21, 128, 96), (190, 40, 50), (176, 110, 0), (25, 30, 40), (100, 108, 120), (225, 228, 233)


def _n(x) -> str:
    return f"{int(x):,}"


class _Pdf:
    def __init__(self):
        from fpdf import FPDF

        pdf = FPDF(format="A4", unit="mm")
        pdf.set_auto_page_break(False)
        pdf.set_margins(14, 12, 14)
        for style, name in (("", "Regular"), ("B", "Bold")):
            pdf.add_font("plex", style, str(FONTS / f"IBMPlexSansArabic-arabic-{name}.ttf"))
            pdf.add_font("plexl", style, str(FONTS / f"IBMPlexSansArabic-latin-{name}.ttf"))
        pdf.set_fallback_fonts(["plexl"])
        pdf.set_text_shaping(use_shaping_engine=True, direction="rtl", script="arab", language="ara")
        pdf.add_page()
        self.pdf = pdf

    def text(self, s: str, size=10, bold=False, color=INK, h=6, align="R", w=0):
        self.pdf.set_font("plex", "B" if bold else "", size)
        self.pdf.set_text_color(*color)
        self.pdf.multi_cell(w, h, s, align=align, new_x="LMARGIN", new_y="NEXT")

    def rule(self, gap=3):
        y = self.pdf.get_y() + gap / 2
        self.pdf.set_draw_color(*LINE)
        self.pdf.line(14, y, 196, y)
        self.pdf.set_y(y + gap / 2)

    def cards(self, items: list[tuple[str, str, str, tuple]]):
        """Up to 4 cards in a row (right to left): (title, big value, one line, color)."""
        pdf, top = self.pdf, self.pdf.get_y()
        n = len(items)
        gap, width = 4, (182 - 4 * (len(items) - 1)) / max(1, n)
        for i, (title, big, line, color) in enumerate(items):
            x = 196 - (i + 1) * width - i * gap
            pdf.set_draw_color(*color)
            pdf.set_line_width(0.5)
            pdf.rect(x, top, width, 30, style="D", round_corners=True, corner_radius=2)
            pdf.set_xy(x + 2, top + 2)
            pdf.set_font("plex", "B", 10)
            pdf.set_text_color(*INK)
            pdf.cell(width - 4, 6, title, align="R")
            pdf.set_xy(x + 2, top + 8)
            pdf.set_font("plex", "B", 18)
            pdf.set_text_color(*color)
            pdf.cell(width - 4, 10, big, align="R")
            pdf.set_xy(x + 2, top + 19)
            pdf.set_font("plex", "", 7.5)
            pdf.set_text_color(*MUTED)
            pdf.multi_cell(width - 4, 4, line, align="R")
        pdf.set_line_width(0.2)
        pdf.set_y(top + 33)


def summary(twin) -> dict:
    """What was cleaned, what was replaced, review decisions: counts only (page and PDF share it)."""
    rep = twin.report or {}
    cleaning = rep.get("cleaning") or {}
    cleaned = {r: int(v.get("total", 0)) for r, v in (cleaning.get("applied") or {}).items() if v.get("total")}
    replaced: dict[str, int] = {}
    filled = {(t["name"], c["name"]): int(t["rows"]) - int(c.get("nulls") or 0)
              for t in (twin.dataset.summary or {}).get("tables", []) for c in t.get("columns", [])}
    for c in rep.get("columns", []):
        if c.get("action") == "pseudonymize" and c.get("kind"):
            rows = filled.get((c["table"], c["column"]),
                              rep.get("input", {}).get("tables", {}).get(c["table"], {}).get("rows", 0))
            replaced[c["kind"]] = replaced.get(c["kind"], 0) + int(rows)
    for k, n in (rep.get("free_text", {}).get("spans_replaced_by_type") or {}).items():
        replaced[k] = replaced.get(k, 0) + int(n)
    totals = (rep.get("free_text", {}).get("review") or {}).get("totals") or {}
    gen = rep.get("generation") or {}
    return {"cleaned": cleaned, "replaced": replaced, "cleaning_decision": rep.get("cleaning_decision"),
            "review": {"auto": int(totals.get("auto", 0)), "admin": int(totals.get("admin", 0)),
                       "pending": int(totals.get("pending", 0)),
                       "cleared_columns": len(gen.get("cleared_columns") or [])}}


def build(twin, org_name: str) -> bytes:
    rep = twin.report or {}
    proof = twin.proof or {}
    ds = twin.dataset
    leak = proof.get("leak", {})
    residual = proof.get("residual") or {}
    validity = proof.get("validity") or {}
    links = proof.get("links") or {}
    safety_ok = leak.get("status") == "PASS" and residual.get("status", "PASS") != "FAIL"
    validity_ok = validity.get("status") != "FAIL"
    links_ok = (links.get("orphans") or 0) == 0
    passed = twin.verdict == "PASS"

    doc = _Pdf()
    doc.text("نَظير · تقرير النظير المقنّع" if twin.mode == "masked" else "نَظير · تقرير النظير الاصطناعي", 16, True)
    doc.text(f"{org_name} · {ds.name} · {twin.created_at.replace(tzinfo=timezone.utc).astimezone(RIYADH):%Y-%m-%d %H:%M}", 10, color=MUTED)
    doc.rule(4)
    if passed:
        sentence = "ناجح: لا يوجد في النظير أي معرّف حقيقي، ويمكن مشاركته."
        if not (validity_ok and links_ok):
            sentence += " ملاحظة جودة لا تمنع المشاركة (أدناه)."
    else:
        sentence = "راسب: وُجد ما يمنع المشاركة، ولن يُشارك هذا النظير."
    doc.text(sentence, 13, True, GREEN if passed else RED, h=8)
    doc.pdf.ln(2)

    doc.text("الأمان", 12, True)
    doc.cards([
        ("التسريب", _n(leak.get("leaks", 0)), f"معرّف حقيقي في {_n(leak.get('cells', 0))} خلية فُحصت كلها.",
         GREEN if leak.get("status") == "PASS" else RED),
        ("فحص البقايا", _n(residual.get("found", 0)), "معرّف صالح بقي دون أن يولّده نَظير.",
         GREEN if residual.get("status", "PASS") != "FAIL" else RED),
    ])
    doc.text("الجودة (لا تمس الخصوصية)", 12, True)
    share = validity.get("share")
    doc.cards([
        ("صلاحية البدائل", f"{round(share * 100)}%" if share is not None else "—",
         "من البدائل تجتاز التحقق الرسمي." if validity_ok else "بعض البدائل لا تجتاز التحقق؛ قد ترفضها الأنظمة. لا يوجد أي تسريب.",
         GREEN if validity_ok else AMBER),
        ("سلامة الروابط", _n(links.get("orphans", 0)), "روابط مكسورة بين الجداول." if links_ok
         else "بعض الروابط انكسرت؛ قد يتأثر التحليل. لا يوجد أي تسريب.", GREEN if links_ok else AMBER),
    ])

    doc.rule()
    sm = summary(twin)
    doc.text("ما نُظِّف قبل التوليد", 11, True)
    doc.text("، ".join(f"{RULE_AR.get(r, r)}: {_n(n)}" for r, n in sm["cleaned"].items())
             or ("تخطّى المدير التنظيف، واستُخدمت البيانات كما رُفعت." if sm["cleaning_decision"] == "skipped"
                 else "لم تحتج البيانات إلى تنظيف."), 9.5)
    doc.text("ما استُبدل", 11, True)
    doc.text("، ".join(f"{KIND_AR.get(k, k)}: {_n(n)}" for k, n in sm["replaced"].items()) or "لا شيء.", 9.5)
    doc.text("القرارات", 11, True)
    rv = sm["review"]
    lines = [f"{_n(rv['auto'])} قرارات اتخذها نَظير تلقائياً، {_n(rv['admin'])} بقرارك."]
    if rv["pending"]:
        lines.append(f"{_n(rv['pending'])} بانتظار القرار.")
    if rv["cleared_columns"]:
        lines.append(f"أكّد المدير أن {rv['cleared_columns']} عموداً لا يحتوي معرّفات.")
    doc.text(" ".join(lines), 9.5)
    if (rep.get("generation") or {}).get("token"):
        doc.text("رمز التحقق: كل صف مشارَك يحمل رمزاً مشفّراً يثبت مصدره ويربطه بسجله الحقيقي عند إعادته، دون أي جدول ربط.", 9.5)

    doc.rule()
    doc.text("حد معروف", 11, True)
    doc.text("نَظير يستبدل المعرّفات المباشرة، ولا يقيس خطر التعرّف على الأشخاص عبر تركيب الأعمدة المتبقية "
             "(مثل العمر والمدينة والتشخيص) في النظير المُقنَّع. للبيانات التي تحتاج هذه الحماية، يُستخدم النظير الاصطناعي.",
             8.5, color=MUTED, h=5)
    doc.pdf.set_y(-14)
    doc.text(f"أُنشئ هذا التقرير في {datetime.now(RIYADH):%Y-%m-%d %H:%M} بتوقيت الرياض · لا يحتوي أي قيمة من البيانات.", 7.5, color=MUTED)
    return bytes(doc.pdf.output())
