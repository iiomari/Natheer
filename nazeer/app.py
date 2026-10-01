"""Nazeer Streamlit UI (runs locally, inside the data owner's environment).

    streamlit run nazeer\\app.py

A guided flow of four steps (data -> detection -> twin -> proof) plus two secondary tabs
("why it works", "try your text"). Demo mode is the default: one button loads the generated
demo dataset and a preset demo key, so nothing has to be typed. Uploads, MySQL, review
overrides, the twin mode and seeds live under "advanced settings".
Presentation only: every number comes from nazeer.pipeline / nazeer.evaluate unchanged.
Originals are shown only in this local session's memory; nothing is cached to disk.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run nazeer\app.py` puts nazeer\ on sys.path; our module names must not
# shadow anything, so import the package from the repository root instead.
_HERE = Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _HERE]
sys.path.insert(0, str(_HERE.parent))

import html  # noqa: E402
import io as _io  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import zipfile  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from nazeer import pipeline  # noqa: E402
from nazeer import ui_logic as ui  # noqa: E402
from nazeer.config import KEY_ENV, KeyConfigError, load_key  # noqa: E402
from nazeer.models import Span  # noqa: E402
from nazeer.mysqlio import MySQLError  # noqa: E402
from nazeer.policy import load_policy  # noqa: E402
from nazeer.safe_log import configure_logging  # noqa: E402
from nazeer.tableio import load_csv_folder, read_csv  # noqa: E402
from nazeer.ui_logic import ACTIONS, KINDS, TAGS, detection_frame, overrides_from_edits, suggestion_frame  # noqa: E402

log = logging.getLogger("nazeer.app")
ROOT = _HERE.parent
DEMO_DIR = Path(os.environ.get("NAZEER_DEMO_DIR", ROOT / "data" / "demo"))
CSS = (_HERE / "static" / "nazeer.css").read_text(encoding="utf-8")

# Public demo key. Used ONLY with the generated demo dataset (no real people) and only when
# NAZEER_KEY is not set, so a demo needs nothing typed. Any other data requires NAZEER_KEY.
DEMO_KEY = b"nazeer-public-demo-key::generated-demo-data-only"
DEMO_KEY_NOTE = "preset demo key (generated demo dataset only; public, not a secret)"

STEPS = ["البيانات", "الكشف", "النظير", "الإثبات"]
AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
KIND_AR = {"SAUDI_ID": "هوية", "MOBILE": "جوال", "IBAN": "آيبان", "EMAIL": "بريد", "PERSON_NAME": "اسم"}
TWIN_AR = {"SAUDI_ID": "هوية بديلة", "MOBILE": "جوال بديل", "IBAN": "آيبان بديل", "EMAIL": "بريد بديل",
           "PERSON_NAME": "اسم بديل"}
ACTION_AR = {"pseudonymize": "بديل", "remap": "مفتاح جديد", "generalize": "تعميم", "replace_spans": "استبدال داخل النص",
             "keep": "كما هو", "drop": "حُذف"}
CHECK_AR = {"leak_scan": "فحص التسريب", "exact_copies": "نسخ مطابقة للأصل", "human_review": "المراجعة البشرية",
            "free_text_replacement": "الاستبدال داخل النص", "detection_vs_golden": "الكشف مقابل مفتاح الإجابة",
            "holdout_split": "فصل بيانات الاختبار قبل التدريب", "dcr": "البُعد عن بيانات التدريب",
            "utility_tstr": "الفائدة للتحليل", "fidelity": "التشابه الإحصائي", "dcr_robustness": "ثبات البُعد عبر التقسيمات",
            "dcr_per_stratum": "البُعد لكل فئة", "synthesizer": "النموذج المولِّد",
            "leak_scan_target_database": "فحص التسريب في قاعدة الهدف"}
STATUS_AR = {"PASS": "ناجح", "FAIL": "راسب", "INFO": "معلومة", "NOT_RUN": "لم يُشغَّل"}
TIPS = {
    "k": "أصغر عدد من الأشخاص يتشاركون نفس العمر والمدينة والجنس. كلما كبر صعُب تمييز الشخص.",
    "recall": "نسبة ما وُجد من كل البيانات الشخصية الموجودة فعلاً.",
    "false_alarm": "شيء عُلِّم كبيانات شخصية وهو ليس كذلك، مثل رقم فاتورة يشبه رقم الهوية.",
    "review": "ثقة أقل: اسم منفرد بلا اسم عائلة، أو رقم بجانب كلمة مثل «فاتورة». يُستبدل احتياطاً ويستحق نظرة بشرية.",
    "rejected": "يشبه رقم هوية لكنه لا يجتاز خوارزمية التحقق الرسمية، فهو ليس هوية.",
    "checksum": "خوارزمية التحقق الرسمية: خانة التحقق في الهوية، وmod-97 في الآيبان.",
    "leak": "نبحث عن كل معرّف حقيقي في كل خلية من النظير، بالكاشف وببحث شامل مستقل عنه.",
    "DCR": "المسافة من كل صف مولَّد إلى أقرب صف حقيقي. إن كانت أقرب من صفوف حقيقية لم يرها النموذج فقد يكون حفظ البيانات.",
    "AUC": "دقة نموذج تنبؤ: 0.5 تخمين عشوائي و1 تنبؤ مثالي.",
    "TSTR": "ندرّب نموذجاً على النظير ونختبره على بيانات حقيقية لم يرها، ثم نقارنه بنموذج مدرَّب على الحقيقي.",
    "masked": "نفس الصفوف، مع استبدال كل معرّف ببديل صالح وتعميم ما يكفي لتصعيب التعرّف.",
    "synthetic": "صفوف جديدة كلياً من نموذج إحصائي تدرّب على 80% من البيانات.",
}
TRY_EXAMPLE = ("راجعنا مطالبة العميل محمد العتيبي، هويته ١١١٠٧٠٤٣٤١ وجواله ٠٥٠ ٣٣١ ٨٨٤٢، والتحويل إلى الآيبان "
               "SA03 8000 0000 6080 1016 7519. رقم الفاتورة 1234567890.")

SYNTH_TRADEOFF = ("تجريبي: يحافظ على دقة نماذج التحليل، لكن صفوفه أقرب قليلاً لبيانات التدريب من صفوف حقيقية "
                  "لم يرها، وهذا الهامش يتذبذب بين التقسيمات.")


# ---------------------------------------------------------------- state

def _init() -> None:
    if "logging" not in st.session_state:
        configure_logging()
        st.session_state["logging"] = True
    for k in ("tables", "source", "source_label", "golden_dir", "golden", "analysis", "labels", "result", "error",
              "applied_fix", "mysql_db", "mysql_schema", "mysql_written", "tracked", "planted", "pending_fix"):
        st.session_state.setdefault(k, None)
    st.session_state.setdefault("overrides", {})
    st.session_state.setdefault("ner_mode", "gazetteer")
    st.session_state.setdefault("mode", "masked")
    st.session_state.setdefault("demo_mode", False)
    st.session_state.setdefault("step", 1)
    st.session_state.setdefault("pending_plant", False)
    st.session_state.setdefault("pending_run", False)


def _reset_after_load() -> None:
    for k in ("analysis", "labels", "golden", "result", "error", "applied_fix", "mysql_written", "tracked", "planted",
              "pending_fix"):
        st.session_state[k] = None
    st.session_state["overrides"] = {}
    st.session_state["step"] = 1


def _reset_all() -> None:
    for k in list(st.session_state):
        if k != "logging":
            del st.session_state[k]


def _go(step: int) -> None:
    st.session_state["step"] = step
    st.session_state["error"] = None


def _md_safe(text: str) -> str:
    return text.replace("$", "\\$")


def _guarded(fn, *args, **kwargs):
    """Run a step; on error show a friendly Arabic message and log type + frames only (never values)."""
    st.session_state["error"] = None
    try:
        return fn(*args, **kwargs)
    except KeyConfigError as e:  # messages are value-free by construction
        st.session_state["error"] = ("المفتاح السري غير مضبوط. بيانات العرض تعمل بمفتاح جاهز، أما بياناتك فتحتاج مفتاحاً "
                                     f"تضبطه في PowerShell قبل تشغيل التطبيق. — {e}")
    except MySQLError as e:  # credential- and value-free by construction
        st.session_state["error"] = f"تعذّر العمل مع MySQL. — {e}"
    except Exception as e:  # noqa: BLE001 - UI boundary
        log.error("UI step %s failed", getattr(fn, "__name__", "step"), exc_info=True)
        st.session_state["error"] = (f"تعذّرت هذه الخطوة. التفاصيل التقنية في سجل الخادم، بلا أي قيم من البيانات. "
                                     f"({type(e).__name__})")
    return None


@st.cache_resource(show_spinner="نحمّل نموذج الأسماء العربي (أول مرة فقط)…")
def _camel_union():
    from nazeer.ner import get_name_detector

    return get_name_detector("union")


def _name_detector():
    if st.session_state.get("ner_mode") == "union":
        return _camel_union()
    return None  # gazetteer default


def _key() -> tuple[bytes, bool]:
    """(key, is_demo_key). The preset key is only ever used for the demo dataset."""
    if os.environ.get(KEY_ENV, "").strip() or not st.session_state["demo_mode"]:
        return load_key(), False
    return DEMO_KEY, True


# ---------------------------------------------------------------- loading

def load_demo() -> None:
    if not (DEMO_DIR / "customers.csv").exists():
        from data_gen import make_demo_data
        make_demo_data.main(["--seed", "42", "--n", "3000", "--out", str(DEMO_DIR)])
    st.session_state.update(tables=load_csv_folder(DEMO_DIR), source="demo dataset (generated, no real people)",
                            source_label="بيانات العرض (مولَّدة، بلا أشخاص حقيقيين)", golden_dir=DEMO_DIR / "_golden",
                            mysql_db=None, mysql_schema=None, demo_mode=True)
    _reset_after_load()


def load_uploads(files) -> None:
    tables = {Path(f.name).stem: read_csv(f) for f in files}
    st.session_state.update(tables=tables, source=f"{len(tables)} uploaded CSV file(s)",
                            source_label=f"{len(tables)} ملف CSV مرفوع", golden_dir=None,
                            mysql_db=None, mysql_schema=None, demo_mode=False)
    _reset_after_load()


def load_mysql_source(database: str) -> None:
    from nazeer import mysqlio

    settings = mysqlio.load_settings()
    tables, schema = mysqlio.load_mysql(settings, database)
    st.session_state.update(tables=tables, source=f"MySQL database {database} (read-only)",
                            source_label=f"قاعدة MySQL ‏{database} (قراءة فقط)", golden_dir=None,
                            mysql_db=database, mysql_schema=schema, demo_mode=False)
    _reset_after_load()


def _connect_mysql() -> None:
    _guarded(load_mysql_source, st.session_state.get("mysql_source") or "")


def _ner_changed() -> None:
    for k in ("analysis", "labels", "golden", "result", "planted", "applied_fix"):
        st.session_state[k] = None


def ensure_analysis() -> None:
    if st.session_state["tables"] is None:
        return
    if st.session_state["analysis"] is None:
        slow = st.session_state.get("ner_mode") == "union"
        msg = "نقرأ الجداول ونبحث عن البيانات الشخصية…" + (" (نموذج الأسماء يحتاج دقائق على المعالج)" if slow else "")
        with st.spinner(msg):
            schema = st.session_state["mysql_schema"]
            an = _guarded(lambda: pipeline.analyze(
                st.session_state["tables"], st.session_state["source"], ner=_name_detector(),
                db_fks=schema.foreign_keys if schema else None, db_pks=schema.primary_keys if schema else None))
        if an is None:
            return
        st.session_state.update(analysis=an, labels=None, tracked=None, golden=None)
    _ensure_derived(st.session_state["analysis"])


def _ensure_derived(an) -> None:
    """Labels, tracked entity and answer-key scores, rebuilt whenever missing (e.g. a browser
    session that was opened before these keys existed survives a code reload)."""
    if st.session_state["labels"] is None:
        st.session_state["labels"] = ui.entity_labels(an)
    if st.session_state["tracked"] not in st.session_state["labels"]:
        st.session_state["tracked"] = ui.default_entity(an)
    golden = st.session_state["golden_dir"]
    if st.session_state["golden"] is None and golden is not None:
        st.session_state["golden"] = pipeline._golden_scores(an, golden)


# ---------------------------------------------------------------- html helpers

_NUMBER = re.compile(r"(?:SA|\+)?[0-9٠-٩۰-۹](?:[0-9٠-٩۰-۹ \-.,/]*[0-9٠-٩۰-۹])?%?")
_ARABIC_LETTER = re.compile(r"[ء-يٮ-ۓ]")


def esc(v) -> str:
    return html.escape(str(v), quote=True)


def ltr(v) -> str:
    """Left-to-right island. Numbers and identifiers are shown in stored order (override);
    text that contains Arabic letters is only isolated, so its letters still join correctly."""
    s = str(v)
    cls = "nz-ltr-text" if _ARABIC_LETTER.search(s) else "nz-ltr"
    return f'<bdi class="{cls}" dir="ltr">{esc(s)}</bdi>'


def num(v, fmt: str = ",") -> str:
    return ltr(format(v, fmt))


def ltr_numbers(text: str) -> str:
    """Escape text and isolate every number (with in-number spaces) left-to-right, so IDs,
    mobiles and IBANs never flip inside Arabic sentences."""
    out, last = [], 0
    for m in _NUMBER.finditer(text):
        out.append(esc(text[last:m.start()]))
        out.append(ltr(m.group()))
        last = m.end()
    out.append(esc(text[last:]))
    return "".join(out)


def cell(v, clip: int | None = None) -> str:
    s = ui._show(v)
    if not s:
        return '<span style="opacity:.4">—</span>'
    if clip and len(s) > clip:
        s = s[:clip] + "…"
    return ltr_numbers(s) if _ARABIC_LETTER.search(s) else ltr(s)


def term(label: str, key: str) -> str:
    return f'<span class="nz-term" tabindex="0" data-tip="{esc(TIPS[key])}">{label}</span>'


def badge(status: str) -> str:
    cls = {"PASS": "pass", "FAIL": "fail"}.get(status, "info")
    sym = {"PASS": "✓ ", "FAIL": "✗ "}.get(status, "")
    return f'<span class="nz-badge {cls}">{ltr(sym + status)}</span>'


def mark_label(status: str, kind: str) -> str:
    if status == "review":
        return f"للمراجعة · {KIND_AR.get(kind, kind)}"
    if status == "rejected":
        return "رُفض"
    if status == "false_alarm":
        return "إنذار كاذب"
    if status == "twin":
        return TWIN_AR.get(kind, kind)
    if status == "leak":
        return "تسريب"
    return KIND_AR.get(kind, kind)


def marked(text: str, marks: list[tuple], css: str = "") -> str:
    out, last = [], 0
    for a, b, status, kind in sorted(marks):
        if a < last:
            continue
        out.append(ltr_numbers(text[last:a]))
        val = text[a:b]
        inner = esc(val) if kind == "PERSON_NAME" else ltr(val)
        lab = mark_label(status, kind)
        out.append(f'<mark class="nz-hl {status}" title="{esc(lab)}"><span class="nz-val">{inner}</span>'
                   f'<span class="nz-lab {status}">{esc(lab)}</span></mark>')
        last = b
    out.append(ltr_numbers(text[last:]))
    return f'<div class="nz-text {css}">{"".join(out)}</div>'


def legend(items: list[tuple[str, str]], lead: str = "", notes: str = "") -> str:
    """Color AND text: every highlight color is shown with its label."""
    chips = "".join(f'<span class="nz-lab {cls}">{esc(lab)}</span>' for cls, lab in items)
    tail = f'<span class="nz-note" style="margin-inline-start:1rem">ما معناها؟ {notes}</span>' if notes else ""
    return f'<div class="nz-legend">{f"<span>{esc(lead)}</span>" if lead else ""}{chips}{tail}</div>'


def show(html_text: str) -> None:
    st.markdown(html_text, unsafe_allow_html=True)


def inject_css() -> None:
    try:
        kind = st.context.theme.type
    except Exception:  # noqa: BLE001 - outside a browser session (tests)
        kind = None
    marker = f'<span class="nz-theme-{kind}"></span>' if kind in ("light", "dark") else ""
    show(f"<style>{CSS}</style>{marker}")


# ---------------------------------------------------------------- header, stepper, tracker

def header() -> None:
    c1, c2 = st.columns([6, 1], vertical_alignment="center")
    c1.markdown('<div class="nz-brand"><span class="nz-logo">نَظير</span><span class="nz-logo-en">Nazeer</span>'
                '<span class="nz-tagline">نسخة من بياناتك بلا أشخاص حقيقيين، وبنفس النتائج</span></div>',
                unsafe_allow_html=True)
    if st.session_state["tables"] is not None:
        c2.button("إعادة البدء", key="reset", on_click=_reset_all, width="stretch")


def stepper(step: int) -> None:
    items = []
    for i, name in enumerate(STEPS, 1):
        cls = "current" if i == step else ("done" if i < step else "")
        items.append(f'<li class="nz-step {cls}">{"✓ " if i < step else ""}{str(i).translate(AR_DIGITS)}. {name}</li>')
    show('<ol class="nz-steps">' + '<li class="nz-arrow">←</li>'.join(items) + "</ol>")


def _track_changed() -> None:
    st.session_state["tracked"] = st.session_state["track_pick"]
    st.session_state["planted"] = None


def entity_word(an) -> str:
    key = ui.entity_key(an.profile)
    return "عميل" if key is None or st.session_state["demo_mode"] or "customer" in key[0].lower() else "سجل"


def tracker(label: str | None = None) -> None:
    an = st.session_state["analysis"]
    labels = st.session_state["labels"] or {}
    if not labels:
        return
    if st.session_state["tracked"] not in labels:
        st.session_state["tracked"] = ui.default_entity(an)
    st.session_state["track_pick"] = st.session_state["tracked"]
    c1, _ = st.columns([2, 3])
    c1.selectbox(label or f"تتبّع {entity_word(an)} عبر كل الخطوات", list(labels), key="track_pick",
                 format_func=lambda v: labels.get(v, v), on_change=_track_changed)


def nav(next_label: str | None, next_key: str | None, next_step: int | None, back: int | None) -> None:
    c1, c2, _ = st.columns([2, 1, 4])
    if next_label:
        c1.button(next_label, key=next_key, type="primary", on_click=_go, args=(next_step,), width="stretch")
    if back:
        c2.button("رجوع", key=f"back_{back}", on_click=_go, args=(back,), width="stretch")


# ---------------------------------------------------------------- step 1: data

def data_table(an, table: str, tracked_rows: list[int], others: int = 4) -> str:
    df = an.tables[table]
    text_cols = {d.column for d in an.detections if d.table == table and d.tag == "FREE_TEXT"}
    rest = [i for i in range(len(df)) if i not in set(tracked_rows)][:others]
    head = "".join(f"<th>{ltr(c)}</th>" for c in df.columns)
    body = []
    for r in tracked_rows + rest:
        tracked = r in tracked_rows
        tds = []
        for j, c in enumerate(df.columns):
            v = df[c].iat[r]
            if c in text_cols:
                td = f'<td class="nz-wrap">{cell(v)}</td>' if tracked else f'<td class="nz-clip">{cell(v, 60)}</td>'
            else:
                td = f"<td>{cell(v)}</td>"
            if j == 0 and tracked:
                td = td.replace("</td>", '<span class="nz-tracked-tag">المتتبَّع</span></td>')
            tds.append(td)
        body.append(f'<tr class="{"tracked" if tracked else ""}">{"".join(tds)}</tr>')
    return (f'<div class="nz-tablewrap"><table class="nz-table"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def step_data() -> None:
    st.header("١. البيانات", anchor=False)
    tables = st.session_state["tables"]
    if tables is None:
        show('<p class="nz-lead">جداول عملاء ومطالبات تبدو عادية… لكن ملاحظاتها النصية تخفي هويات وجوالات '
             "وآيبانات، بأرقام عربية وبمسافات.</p>")
        c1, _ = st.columns([2, 5])
        c1.button("تحميل بيانات العرض", key="demo", type="primary", on_click=_guarded, args=(load_demo,),
                  width="stretch")
        show('<p class="nz-note">بيانات مولَّدة بالكامل لعملاء وهميين، ومعها مفتاح عرض جاهز: لا شيء يُرفع أو يُكتب. '
             "لرفع ملفاتك أو الاتصال بقاعدة MySQL افتح «إعدادات متقدمة» في الأسفل.</p>")
        return
    an = st.session_state["analysis"]
    if an is None:
        return
    pills = [f'<span class="nz-pill">المصدر: <b>{esc(st.session_state["source_label"] or "")}</b></span>']
    pills += [f'<span class="nz-pill">{ltr(n)}: <b>{len(df):,}</b> صف · {df.shape[1]} أعمدة</span>'
              for n, df in tables.items()]
    show('<div class="nz-strip">' + "".join(pills) + "</div>")
    tracker()
    rows = ui.entity_rows(an, st.session_state["tracked"])
    for name in tables:
        show(f'<h4 style="margin:.9rem 0 .4rem">{ltr(name)}</h4>' + data_table(an, name, rows.get(name, [])))
    show('<p class="nz-note">الصفوف المظلّلة تخص العميل المتتبَّع. سنتابعه في كل خطوة.</p>')
    nav("التالي: ماذا وجد نظير؟", "next_1", 2, None)


# ---------------------------------------------------------------- step 2: detection

def _found_card(title: str, css: str, who: dict, total: int | None, has_key: bool) -> str:
    found = f'<div class="nz-big">{num(who["found"])}</div>'
    found_sub = (f'<div class="nz-sub">وجدت من أصل {ltr(f"{total:,}")} معرّفاً مخفياً</div>' if has_key
                 else '<div class="nz-sub">علّمتها كبيانات شخصية</div>')
    fa = who["false_alarms"]
    fa_html = (f'<div class="nz-mid">{ltr(f"{fa:,}")}</div>' if fa is not None
               else '<div class="nz-mid">—</div>')
    fa_sub = f'<div class="nz-sub">{term("إنذارات كاذبة", "false_alarm")}</div>'
    if fa is None:
        fa_sub += '<div class="nz-sub">غير معروفة بلا مفتاح إجابة</div>'
    rec = (f'<div class="nz-sub">{term("نسبة ما وُجد", "recall")}: {num(who["recall"], ".1%")}</div>'
           if who.get("recall") is not None else "")
    return (f'<div class="nz-card {css}"><h4>{title}</h4><div class="nz-row"><div>{found}{found_sub}</div>'
            f"<div>{fa_html}{fa_sub}</div></div>{rec}</div>")


def _column_pills(an) -> str:
    direct = [f"{ltr(d.column)} ({KIND_AR.get(d.kind, '')})" for d in an.detections if d.tag == "DIRECT_ID"]
    quasi = [ltr(d.column) for d in an.detections if d.tag == "QUASI_ID"]
    text = [ltr(f"{d.table}.{d.column}") for d in an.detections if d.tag == "FREE_TEXT"]
    links = [f"{ltr(f'{f.child_table}.{f.child_column}')} ← {ltr(f'{f.parent_table}.{f.parent_column}')}"
             for f in an.profile.foreign_keys]
    pills = []
    if direct:
        pills.append(f'<span class="nz-pill">معرّفات في الأعمدة: <b>{"، ".join(direct)}</b></span>')
    if quasi:
        pills.append(f'<span class="nz-pill">تكشف الشخص إذا اجتمعت: <b>{"، ".join(quasi)}</b></span>')
    if text:
        pills.append(f'<span class="nz-pill">نص حر فُحص: <b>{"، ".join(text)}</b></span>')
    if links:
        pills.append(f'<span class="nz-pill">روابط: <b>{"، ".join(links)}</b></span>')
    pending = sum(d.needs_review for d in an.detections)
    if pending:
        pills.append(f'<span class="nz-pill warn">{pending} عمود يحتاج مراجعة بشرية: «إعدادات متقدمة»</span>')
    return '<div class="nz-strip">' + "".join(pills) + "</div>"


def _best_note(an) -> tuple[str, str, int] | None:
    cells = {(sp.table, sp.column, sp.row) for sp in an.spans}
    if not cells:
        return None
    return max(sorted(cells), key=lambda c: ui.note_score(an, c))


def step_detect() -> None:
    an = st.session_state["analysis"]
    st.header("٢. الكشف", anchor=False)
    show('<p class="nz-lead">نفس الملاحظات بعينين: أداة تقليدية تبحث بأنماط بسيطة، ونَظير يفهم الأرقام العربية '
         f'والمسافات و{term("التحقق الرسمي", "checksum")}.</p>')
    summary = ui.detection_summary(an, st.session_state["golden"])
    c_base, c_naz = st.columns(2)
    c_base.markdown(_found_card("أداة تقليدية", "muted", summary["baseline"], summary["total"], summary["has_key"]),
                    unsafe_allow_html=True)
    c_naz.markdown(_found_card("نَظير", "twin", summary["nazeer"], summary["total"], summary["has_key"]),
                   unsafe_allow_html=True)

    cells = ui.entity_notes(an, st.session_state["tracked"])
    title = f"ملاحظات {(st.session_state['labels'] or {}).get(st.session_state['tracked'], '')}"
    if not cells:
        best = _best_note(an)
        cells, title = ([best] if best else []), "ملاحظة من البيانات"
    if cells:
        st.subheader(title, anchor=False)
        if len(cells) > 1:
            c1, _ = st.columns([1, 4])
            pick = c1.selectbox("الملاحظة", cells, key="note_pick",
                                format_func=lambda c: f"ملاحظة {cells.index(c) + 1} من {len(cells)}")
        else:
            pick = cells[0]
        text, base_marks, naz_marks = ui.cell_marks(an, pick)
        lb, ln = st.columns(2)
        lb.markdown('<h4 style="margin:.2rem 0 .4rem">أداة تقليدية</h4>' + marked(text, base_marks),
                    unsafe_allow_html=True)
        ln.markdown('<h4 class="nz-title-twin" style="margin:.2rem 0 .4rem">نَظير</h4>' + marked(text, naz_marks),
                    unsafe_allow_html=True)
        show(legend([("", "هوية"), ("", "جوال"), ("", "آيبان"), ("", "بريد"), ("", "اسم"),
                     ("review", "للمراجعة"), ("rejected", "رُفض"), ("false_alarm", "إنذار كاذب")],
                    lead="بيانات شخصية:",
                    notes=f'{term("للمراجعة", "review")} · {term("رُفض", "rejected")} · '
                          f'{term("إنذار كاذب", "false_alarm")}'))
    show(_column_pills(an))
    nav("التالي: ولّد النظير", "next_2", 3, 1)


# ---------------------------------------------------------------- step 3: twin

def _run_masked(an, apply_fix: str | None):
    key, is_demo = _key()
    res = pipeline.run_masked(an, load_policy(pipeline.DEFAULT_POLICY), key, st.session_state["overrides"],
                              apply_fix=apply_fix, golden_dir=st.session_state["golden_dir"])
    if is_demo:
        res.report["key"] = {"source": DEMO_KEY_NOTE}
    return res


def _write_to_mysql(target_db: str) -> None:
    from nazeer import mysqlio

    mysqlio.check_target(st.session_state["mysql_db"], target_db)
    settings = mysqlio.load_settings()
    entry = pipeline.write_twin_to_mysql(st.session_state["result"], st.session_state["analysis"], settings,
                                         target_db, st.session_state["mysql_db"], st.session_state["mysql_schema"])
    st.session_state["mysql_written"] = entry


def run_twin() -> None:
    an = st.session_state["analysis"]
    mode = st.session_state["mode"]
    msg = ("نولّد النظير ثم نفحص كل خلية فيه… (قرابة نصف دقيقة على بيانات العرض)" if mode == "masked" else
           "ندرّب النموذج الإحصائي ونقيس الفائدة والخصوصية… (قرابة دقيقة)")
    with st.spinner(msg):
        if mode == "masked":
            res = _guarded(lambda: _run_masked(an, None))
        else:
            res = _guarded(lambda: pipeline.run_synthetic(
                an, load_policy(pipeline.DEFAULT_POLICY), st.session_state["overrides"],
                target=st.session_state.get("target") or None, method=st.session_state.get("method", "stratified_copula"),
                seed=int(st.session_state.get("seed") or 0), golden_dir=st.session_state["golden_dir"]))
        st.session_state.update(result=res, applied_fix=None, planted=None, mysql_written=None)
        if res is not None and st.session_state.get("write_db"):
            _guarded(_write_to_mysql, st.session_state.get("target_db") or "")


def _record_table(an, res, table: str, row: int) -> str:
    comp = ui.compare_rows(an.tables[table], res.twin[table], [row])
    if not comp:
        return ""
    actions = ui.column_actions(res)
    body = []
    for col, (o, t, changed) in comp[0].items():
        what = ACTION_AR.get(actions.get((table, col), ""), "") if changed else "كما هو"
        body.append(f'<tr><td>{ltr(col)}</td><td>{cell(o)}</td><td class="{"changed" if changed else "same"}">'
                    f'{cell(t)}</td><td>{esc(what)}</td></tr>')
    return ('<div class="nz-tablewrap"><table class="nz-table"><thead><tr><th>الحقل</th><th class="real">الأصل</th>'
            '<th class="twin">النظير</th><th>ما حدث</th></tr></thead><tbody>' + "".join(body) + "</tbody></table></div>")


def _side_table(df: pd.DataFrame, rows: list[int], cols: list[str], changed: set | None = None,
                css: str = "") -> str:
    head = "".join(f"<th>{ltr(c)}</th>" for c in cols)
    body = []
    for r in rows:
        tds = "".join(f'<td class="{"changed" if changed and (r, c) in changed else ""}">{cell(df[c].iat[r])}</td>'
                      for c in cols)
        body.append(f"<tr>{tds}</tr>")
    return (f'<div class="nz-tablewrap"><table class="nz-table {css}"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def _totals_strip(an, res) -> None:
    tot = ui.twin_totals(an, res)
    pills = []
    for t in tot["tables"]:
        eq = t["rows_original"] == t["rows_twin"]
        pills.append(f'<span class="nz-pill {"ok" if eq else "warn"}">صفوف {ltr(t["table"])}: '
                     f'<b>{num(t["rows_original"])}</b> {"=" if eq else "≠"} <b>{num(t["rows_twin"])}</b></span>')
        for s in t["sums"]:
            eq = abs(s["original"] - s["twin"]) < 1e-6
            pills.append(f'<span class="nz-pill {"ok" if eq else "warn"}">مجموع {ltr(s["column"])}: '
                         f'<b>{num(s["original"], ",.2f")}</b> {"=" if eq else "≠"} <b>{num(s["twin"], ",.2f")}</b></span>')
    if tot["links"]:
        pills.append(f'<span class="nz-pill {"ok" if tot["orphans"] == 0 else "warn"}">روابط مكسورة: '
                     f'<b>{ltr(tot["orphans"])}</b></span>')
    show('<div class="nz-strip">' + "".join(pills) + "</div>")
    if tot["all_same"]:
        show('<p class="nz-lead"><b>نفس الأعداد والمجاميع والروابط — بدون عميل حقيقي.</b></p>')
    else:
        show('<p class="nz-lead"><b>تنبيه: يوجد فرق في الأعداد أو المجاميع أو الروابط، والأرقام أعلاه تبيّنه.</b></p>')


def _note_pair(an, res, cell_: tuple[str, str, int], headers: bool = False) -> None:
    t, c, r = cell_
    text, _, naz_marks = ui.cell_marks(an, cell_)
    twin_text = res.twin[t][c].iat[r]
    c1, c2 = st.columns(2)
    h1 = '<div class="nz-title-real">الأصل</div>' if headers else ""
    h2 = '<div class="nz-title-twin">النظير</div>' if headers else ""
    c1.markdown(h1 + marked(text, [m for m in naz_marks if m[2] in ("hit", "review")], "real"), unsafe_allow_html=True)
    c2.markdown(h2 + marked(twin_text, ui.twin_marks(twin_text), "twin"), unsafe_allow_html=True)


def twin_view_masked(an, res) -> None:
    if res.twin_withheld:
        st.error("فشل فحص التسريب، لذلك حُجب النظير ولم يُعرض. التفاصيل في الخطوة ٤.")
        return
    tracker(f"ال{entity_word(an)} المتتبَّع")
    key = ui.entity_key(an.profile)
    rows = ui.entity_rows(an, st.session_state["tracked"])
    if key and rows.get(key[0]):
        st.subheader("قبل ← بعد", anchor=False)
        show(_record_table(an, res, key[0], rows[key[0]][0]))
    text_cols = {(d.table, d.column) for d in an.detections if d.tag == "FREE_TEXT"}
    for table, child_rows in rows.items():
        if key and table == key[0] or not child_rows or table not in res.twin:
            continue
        cols = [c for c in an.tables[table].columns if (table, c) not in text_cols and c in res.twin[table].columns]
        comp = ui.compare_rows(an.tables[table], res.twin[table], child_rows, cols)
        changed = {(r, c) for r, row in zip(child_rows, comp) for c, (_, _, ch) in row.items() if ch}
        show(f'<h4 style="margin:1rem 0 .4rem">{ltr(table)} · {len(child_rows)} صفوف</h4>')
        c1, c2 = st.columns(2)
        c1.markdown('<div class="nz-title-real">الأصل</div>'
                    + _side_table(an.tables[table], child_rows, cols), unsafe_allow_html=True)
        c2.markdown('<div class="nz-title-twin">النظير</div>'
                    + _side_table(res.twin[table], child_rows, cols, changed, "twin"), unsafe_allow_html=True)
    notes = [c for c in ui.entity_notes(an, st.session_state["tracked"]) if c[0] in res.twin]
    if notes:
        show('<h4 style="margin:1rem 0 .4rem">الملاحظة</h4>')
        _note_pair(an, res, notes[0], headers=True)
    if len(notes) > 1:
        with st.expander(f"ملاحظات أخرى لنفس ال{entity_word(an)} ({len(notes) - 1})"):
            for cell_ in notes[1:]:
                _note_pair(an, res, cell_)
    show(legend([("", "معرّف حقيقي"), ("twin", "بديل صالح")],
                notes='<span class="nz-title-twin">●</span> خلية تغيّرت في النظير'))
    _totals_strip(an, res)


def twin_view_synthetic(an, res) -> None:
    syn = res.report["synthetic"]
    name = syn["twin_table"]
    orig = res.extras["originals"][name]
    twin = res.twin[name]
    cols = [c for c in twin.columns if c in orig.columns and twin[c].astype(str).str.len().mean() < 40][:8]
    show(f'<p class="nz-lead">{term("صفوف جديدة كلياً", "synthetic")} بنفس الأنماط الإحصائية؛ '
         "لا يوجد صف مقابل لكل شخص، لذلك لا يُتتبَّع عميل هنا.</p>")
    c1, c2 = st.columns(2)
    c1.markdown('<div class="nz-title-real">عينة من بيانات التدريب الحقيقية</div>'
                + _side_table(orig, list(range(min(6, len(orig)))), cols), unsafe_allow_html=True)
    c2.markdown('<div class="nz-title-twin">عينة من النظير الاصطناعي</div>'
                + _side_table(twin, list(range(min(6, len(twin)))), cols, None, "twin"), unsafe_allow_html=True)
    pills = [f'<span class="nz-pill">صفوف التدريب: <b>{num(syn["rows"]["real_train"])}</b></span>',
             f'<span class="nz-pill">صفوف النظير: <b>{num(syn["rows"]["twin"])}</b></span>']
    for c in cols:
        o, t = ui._as_number(orig[c]), ui._as_number(twin[c])
        if o is not None and t is not None and c in syn["modelled_columns"]:
            pills.append(f'<span class="nz-pill">متوسط {ltr(c)}: <b>{ltr(f"{o.mean():,.1f}")}</b> مقابل '
                         f'<b>{ltr(f"{t.mean():,.1f}")}</b></span>')
    show('<div class="nz-strip">' + "".join(pills) + "</div>")
    show(f'<p class="nz-note">{esc(SYNTH_TRADEOFF)}</p>')


def step_twin() -> None:
    an = st.session_state["analysis"]
    res = st.session_state["result"]
    mode = st.session_state["mode"]
    st.header("٣. النظير", anchor=False)
    if res is None or res.mode != mode:
        if mode == "masked":
            show(f'<p class="nz-lead">{term("النظير المقنّع", "masked")}: نستبدل كل معرّف ببديل صالح ومتّسق '
                 "في كل الجداول والنصوص، ونعمّم العمر، ثم نفحص النتيجة كاملة.</p>")
        else:
            show(f'<p class="nz-lead">{term("النظير الاصطناعي", "synthetic")} (تجريبي): صفوف جديدة كلياً من نموذج '
                 "إحصائي، مع إبقاء 20% من البيانات جانباً لاختباره.</p>")
            show(f'<p class="nz-note">{esc(SYNTH_TRADEOFF)}</p>')
        c1, c2, _ = st.columns([2, 1, 4])
        c1.button("ولّد النظير", key="run", type="primary", on_click=_run_clicked, width="stretch")
        c2.button("رجوع", key="back_2", on_click=_go, args=(2,), width="stretch")
        return
    if res.mode == "masked":
        twin_view_masked(an, res)
    else:
        twin_view_synthetic(an, res)
    c1, c2, c3, _ = st.columns([2, 2, 1, 2])
    c1.button("التالي: الإثبات", key="next_3", type="primary", on_click=_go, args=(4,), width="stretch")
    c2.button("أعد التوليد بالإعدادات الحالية", key="rerun", on_click=_run_clicked, width="stretch")
    c3.button("رجوع", key="back_2", on_click=_go, args=(2,), width="stretch")


# ---------------------------------------------------------------- step 4: proof

def _card(title: str, status: str, big: str, sub: str, explain: str) -> str:
    css = {"PASS": "pass", "FAIL": "fail"}.get(status, "muted")
    return (f'<div class="nz-card {css}"><h4>{title}</h4>{badge(status)}'
            f'<div class="nz-big" style="margin-top:.4rem">{big}</div><div class="nz-sub">{sub}</div>'
            f'<p class="nz-sub" style="margin:.5rem 0 0">{explain}</p></div>')


def _failed_ar(name: str) -> str:
    base, _, table = name.partition("[")
    if base == "k_anonymity":
        return "خطر التعرّف بالتركيب"
    return CHECK_AR.get(base, base)


def _verdict(rep: dict, planted: dict | None = None) -> None:
    if planted:
        show('<div class="nz-verdict fail"><b>النتيجة مع التسريب المزروع</b>' + badge("FAIL")
             + "<span>كان النظير سيُحجب تلقائياً. النظير الفعلي لم يتغيّر، ونتيجته "
             + STATUS_AR[rep["verdict"]] + ".</span></div>")
        return
    if rep["verdict"] == "PASS":
        text = "النظير جاهز: كل الفحوصات الحاسمة ناجحة."
    else:
        text = "لم ينجح بعد. الفحص الذي لم ينجح: " + "، ".join(dict.fromkeys(_failed_ar(n) for n in rep["failed_checks"]))
    show(f'<div class="nz-verdict {"pass" if rep["verdict"] == "PASS" else "fail"}"><b>النتيجة</b>'
         f'{badge(rep["verdict"])}<span>{esc(text)}</span></div>')


def _apply_fix_clicked() -> None:
    """The fix chosen under "fix options", else the recommended one (suggestions are best first)."""
    k = next(iter(st.session_state["result"].report.get("k_anonymity", {}).values()), {})
    suggested = [f["name"] for f in k.get("suggestions", [])]
    pick = st.session_state.get("fix_pick")
    st.session_state["pending_fix"] = pick if pick in suggested else (suggested[0] if suggested else None)


def _plant_clicked() -> None:
    st.session_state["pending_plant"] = True


def _unplant_clicked() -> None:
    st.session_state["planted"] = None


def _run_clicked() -> None:
    st.session_state["pending_run"] = True


def _do_pending(an) -> None:
    """Slow actions requested by a button, run at the top of the next script run (with a spinner)
    so every widget below still renders in that run and errors are shown."""
    if st.session_state["pending_run"]:
        st.session_state["pending_run"] = False
        run_twin()
    fix = st.session_state["pending_fix"]
    if fix:
        st.session_state["pending_fix"] = None
        with st.spinner("نطبّق الإصلاح المقترح ونعيد توليد النظير وفحصه…"):
            res = _guarded(lambda: _run_masked(an, fix))
        if res is not None:
            st.session_state.update(result=res, applied_fix=fix, planted=None)
    if st.session_state["pending_plant"]:
        st.session_state["pending_plant"] = False
        with st.spinner("نزرع رقم هوية حقيقياً داخل ملاحظة في نسخة من النظير، ثم نشغّل فحص التسريب…"):
            st.session_state["planted"] = _guarded(lambda: ui.plant_leak(
                an, st.session_state["result"], st.session_state["tracked"], st.session_state["overrides"]))


def proof_masked(an, res) -> None:
    p = ui.proof(an, res)
    planted = st.session_state["planted"]
    cols = st.columns(4)

    # 1. leak
    leak = p["leak"]
    if planted:
        pl = planted["leak"]
        n = sum(pl["leaked_by_kind"].values())
        cols[0].markdown(_card(term("تسريب", "leak"), pl["verdict"], ltr(n),
                               "تسريب زرعناه للتجربة، والتقطه الفحص",
                               "لو كان حقيقياً لحُجب النظير تلقائياً ولم يُسلَّم."), unsafe_allow_html=True)
        cols[0].button("أزل التسريب المزروع", key="unplant_leak", on_click=_unplant_clicked, width="stretch")
    else:
        sub = f"معرّف حقيقي في {num(leak['cells'])} خلية"
        explain = ("بحثنا عن كل معرّف حقيقي في كل خلية من النظير، ولم نجد شيئاً." if leak["status"] == "PASS"
                   else "وُجدت معرّفات حقيقية في النظير، لذلك حُجب.")
        cols[0].markdown(_card(term("تسريب", "leak"), leak["status"], ltr(leak["leaks"]), sub, explain),
                         unsafe_allow_html=True)
        if not res.twin_withheld:
            cols[0].button("ازرع تسريباً", key="plant_leak", on_click=_plant_clicked, width="stretch")

    # 2. validity of the fakes
    v = p["validity"]
    if v is None:
        cols[1].markdown(_card("صلاحية البدائل", "NOT_RUN", "—", "النظير محجوب", "لا يُقاس على نظير محجوب."),
                         unsafe_allow_html=True)
    else:
        share = f"{v['share']:.0%}" if v["share"] is not None else "—"
        kinds = "، ".join(ltr(c.split(".")[-1]) for c in v["columns"])
        cols[1].markdown(_card("صلاحية البدائل", v["status"], ltr(share),
                               f"من البدائل تجتاز {term('التحقق الرسمي', 'checksum')} ({kinds})",
                               "كل هوية وجوال بديل صالح، فيعمل في أنظمة الاختبار كأنه حقيقي."), unsafe_allow_html=True)

    # 3. links
    lk = p["links"]
    if lk is None:
        cols[2].markdown(_card("سلامة الروابط", "NOT_RUN", "—", "النظير محجوب", "لا تُقاس على نظير محجوب."),
                         unsafe_allow_html=True)
    else:
        cols[2].markdown(_card("سلامة الروابط", lk["status"], ltr(lk["orphans"]), "روابط مكسورة بين الجداول",
                               "كل مطالبة ما زالت مرتبطة بعميلها بعد الاستبدال."), unsafe_allow_html=True)

    # 4. k-anonymity
    k = p["k"]
    if k is None:
        cols[3].markdown(_card("خطر التعرّف بالتركيب", "NOT_RUN", "—", "لا أعمدة شبه معرِّفة",
                               "لا يوجد ما يُجمع للتعرّف على شخص."), unsafe_allow_html=True)
        return
    quasi = "، ".join(ltr(c) for c in k["quasi_columns"])
    title = f"خطر التعرّف بالتركيب ({term('k', 'k')})"
    if k.get("applied_fix"):
        f = k["applied_fix"]
        big = ltr(f"k = {k['k_before']} → {k['k_after']}")
        sub = f"بعد الإصلاح (الحد الأدنى {ltr(k['k_min'])}) · أُخفيت قيم {ltr(f['rows_affected'])} صفاً"
        explain = f"كل شخص يشبهه {ltr(k['k_after'])} على الأقل في {quasi}. فشل ما قبل الإصلاح باقٍ في التقرير."
    else:
        big = ltr(f"k = {k['k_after']}")
        sub = f"الحد الأدنى {ltr(k['k_min'])} · {ltr(k['rows_in_small_classes_before'])} صفاً في مجموعات صغيرة"
        explain = (f"كل شخص يشبهه {ltr(k['k_after'])} على الأقل في {quasi}." if k["status"] == "PASS"
                   else f"يمكن تمييز بعض الأشخاص بـ {quasi} معاً.")
    cols[3].markdown(_card(title, k["status"], big, sub, explain), unsafe_allow_html=True)
    if k["status"] == "FAIL" and k["suggestions"]:
        cols[3].button("طبّق الإصلاح المقترح", key="apply_fix", type="primary", on_click=_apply_fix_clicked,
                       width="stretch")

    if planted:
        show(f'<h4 style="margin:1rem 0 .4rem">الملاحظة بعد زرع التسريب ({ltr(planted["table"])}، صف '
             f'{ltr(planted["row"])})</h4>')
        show(marked(planted["text"], [(planted["start"], planted["end"], "leak", planted["kind"])], "twin"))
        found = [ltr(x["table"] + "." + x["column"]) + " صف " + ltr(x["row"]) for x in planted["leak"]["locations"]]
        show(f'<p class="nz-note">زرعنا {KIND_AR.get(planted["kind"], "")} العميل الحقيقية بأرقام عربية ومسافات في '
             f'نسخة من النظير فقط. فحص التسريب وجدها في: {"، ".join(found) or "—"}. النظير الفعلي لم يتغيّر.</p>')
    if k["suggestions"] and not k.get("applied_fix"):
        with st.expander("خيارات الإصلاح (المقترح أولاً)"):
            frame = suggestion_frame(k)
            st.dataframe(frame, hide_index=True, width="stretch")
            st.selectbox("الإصلاح الذي سيُطبَّق", [f["name"] for f in k["suggestions"]], key="fix_pick")


def proof_synthetic(res) -> None:
    rep = res.report
    check = {c["name"]: c for c in rep["checks"]}
    leak = rep["leak_scan"]
    cols = st.columns(4)
    n = sum(leak["leaked_by_kind"].values())
    cols[0].markdown(_card(term("تسريب", "leak"), leak["verdict"], ltr(n),
                           f"معرّف حقيقي في {num(leak['cells_scanned'])} خلية",
                           "المعرّفات في النظير الاصطناعي مولَّدة من جديد ولا تساوي أي أصل."), unsafe_allow_html=True)
    copies = check["exact_copies"]
    cols[1].markdown(_card("نسخ مطابقة", copies["status"], ltr(copies["value"]), "صف منسوخ من بيانات التدريب",
                           "لا يوجد صف في النظير يطابق صفاً حقيقياً."), unsafe_allow_html=True)
    d = rep["privacy"]["dcr"]
    cols[2].markdown(_card(f"البُعد عن البيانات الحقيقية ({term('DCR', 'DCR')})", check["dcr"]["status"],
                           ltr(f"{d['share_twin_closer_to_train_than_holdout']:.0%}"),
                           f"من صفوف النظير أقرب للتدريب منها لبيانات لم يرها (المثالي 50%)",
                           f"الوسيط {ltr(d['median_dcr_twin_to_train'])} مقابل {ltr(d['median_dcr_holdout_to_train'])}"),
                     unsafe_allow_html=True)
    u = rep.get("utility", {})
    ut = check.get("utility_tstr")
    if u.get("models"):
        best = max(u["models"].values(), key=lambda m: m["real"]["auc"] or 0)
        cols[3].markdown(_card(f"الفائدة للتحليل ({term('TSTR', 'TSTR')})", ut["status"],
                               ltr(f"{u['max_auc_drop']:.4f}"),
                               f"أكبر انخفاض في {term('AUC', 'AUC')}: {num(best['real']['auc'], '.3f')} ← "
                               f"{num(best['twin']['auc'], '.3f')}",
                               "نموذج تدرّب على النظير يتنبأ تقريباً مثل نموذج تدرّب على الحقيقي."),
                         unsafe_allow_html=True)
    else:
        cols[3].markdown(_card("الفائدة للتحليل", "NOT_RUN", "—", "لم يُحدَّد عمود هدف",
                               "حدّد عموداً للتنبؤ في «إعدادات متقدمة»."), unsafe_allow_html=True)
    show(f'<p class="nz-note">{esc(SYNTH_TRADEOFF)}</p>')


def twin_zip(result: pipeline.RunResult) -> bytes:
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if not result.twin_withheld:
            for name, df in result.twin.items():
                z.writestr(f"twin/{name}.csv", df.to_csv(index=False, lineterminator="\n"))
        z.writestr("report.json", json.dumps(result.report, ensure_ascii=False, indent=2, default=str))
    return buf.getvalue()


def _checks_table(rep: dict) -> str:
    rows = []
    for c in rep["checks"]:
        base, _, table = c["name"].partition("[")
        name = ("خطر التعرّف بالتركيب" + (" قبل الإصلاح" if base.endswith("before_fix") else "")
                if base.startswith("k_anonymity") else CHECK_AR.get(base, base))
        rows.append(f'<tr><td>{esc(name)}</td><td>{badge(c["status"])}</td>'
                    f'<td>{"نعم" if c["blocking"] else ""}</td><td class="nz-prose"><bdi class="nz-ltr-text" dir="ltr">'
                    f'{esc(c["detail"])}</bdi></td></tr>')
    return ('<div class="nz-tablewrap"><table class="nz-table"><thead><tr><th>الفحص</th><th>النتيجة</th>'
            '<th>يحسم النتيجة</th><th>التفاصيل</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def step_proof() -> None:
    an = st.session_state["analysis"]
    res = st.session_state["result"]
    rep = res.report
    st.header("٤. الإثبات", anchor=False)
    _verdict(rep, st.session_state["planted"] if rep["mode"] == "masked" else None)
    if rep["mode"] == "masked":
        proof_masked(an, res)
    else:
        proof_synthetic(res)

    written = rep.get("mysql_output")
    if written:
        if written.get("written"):
            leak = written["leak_scan_of_target"]
            ok = leak["verdict"] == "PASS" and written["row_counts_match"]
            (st.success if ok else st.error)(
                f"كُتب النظير في قاعدة MySQL ‏{written['target_database']}، ثم قُرئ منها وفُحص: "
                f"{STATUS_AR[leak['verdict']]} ({sum(leak['leaked_by_kind'].values())} معرّف في "
                f"{leak['cells_scanned']:,} خلية).")
        else:
            st.warning("لم يُكتب النظير في قاعدة البيانات لأنه محجوب.")

    c1, c2, _ = st.columns([2, 1, 4])
    c1.download_button("تنزيل النظير والتقرير (zip)" if not res.twin_withheld else "تنزيل التقرير (zip)",
                       data=twin_zip(res), file_name=f"nazeer-{res.run_id}.zip", mime="application/zip", key="dl",
                       width="stretch")
    c2.button("رجوع", key="back_3", on_click=_go, args=(3,), width="stretch")
    with st.expander("كل الفحوصات"):
        show(_checks_table(rep))
    with st.expander("التقرير الكامل (JSON)"):
        st.json(rep, expanded=False)
    with st.expander("حدود معروفة"):
        for line in rep["limitations"]:
            st.markdown(f"- {_md_safe(line)}")


# ---------------------------------------------------------------- advanced settings

def _review_editor(an) -> None:
    pending = sum(d.needs_review for d in an.detections)
    st.markdown("**مراجعة الكشف وتعديله**" + (f" · {pending} عمود يحتاج مراجعة" if pending else ""))
    st.caption("غيّر وسم العمود أو نوع المعرّف أو الإجراء، أو علّم «reviewed» للتأكيد. كل تعديل يُسجَّل في التقرير، "
               "وفحص التسريب يبقى يبحث عن كل معرّف اكتُشف مهما غيّرت هنا.")
    base = detection_frame(an, st.session_state["overrides"])
    edited = st.data_editor(
        base, key="overrides_editor", hide_index=True, width="stretch",
        disabled=["table", "column", "type", "confidence", "needs review", "why"],
        column_config={
            "tag": st.column_config.SelectboxColumn("tag", options=TAGS, required=True),
            "identifier": st.column_config.SelectboxColumn("identifier", options=KINDS),
            "action": st.column_config.SelectboxColumn("action", options=ACTIONS, required=True,
                                                       help="policy = use config/policy.yaml"),
            "reviewed": st.column_config.CheckboxColumn("reviewed"),
        })
    overrides, problems = overrides_from_edits(an, edited)
    st.session_state["overrides"] = overrides
    for msg in problems:
        st.warning(msg)
    if overrides:
        st.info(f"{len(overrides)} تعديل بشري سيُطبَّق ويُسجَّل: " + "، ".join(overrides))


def advanced() -> None:
    an = st.session_state["analysis"]
    with st.expander("إعدادات متقدمة"):
        st.markdown("**مصدر البيانات**")
        c1, c2 = st.columns(2)
        with c1:
            files = st.file_uploader("ارفع ملفات CSV (ملف لكل جدول)", type="csv", accept_multiple_files=True,
                                     key="upload")
            if files:
                st.button("حمّل الملفات المرفوعة", key="load_uploads", on_click=_guarded, args=(load_uploads, files))
        with c2:
            st.text_input("قاعدة MySQL المصدر (قراءة فقط)", value="nazeer_prod_demo", key="mysql_source")
            st.caption("بيانات الدخول من NAZEER_MYSQL_* أو ملف .env، ولا تُكتب في هذه الصفحة أبداً.")
            st.button("اتصل بـ MySQL", key="mysql_connect", on_click=_connect_mysql)
        st.divider()
        st.radio("كشف الأسماء في النص", ["gazetteer", "union"], key="ner_mode", horizontal=True,
                 on_change=_ner_changed,
                 format_func=lambda m: {"gazetteer": "سريع (قوائم الأسماء العربية)",
                                        "union": "أعلى استدعاء (CamelBERT مع القوائم، نحو 0.1 ث لكل ملاحظة)"}[m])
        st.radio("نوع النظير", ["masked", "synthetic"], key="mode", horizontal=True,
                 format_func=lambda m: {"masked": "مقنّع (الافتراضي): نفس الصفوف ببدائل صالحة",
                                        "synthetic": "اصطناعي (تجريبي): صفوف جديدة كلياً"}[m])
        if st.session_state["mode"] == "synthetic":
            st.caption(SYNTH_TRADEOFF)
            has_amount = an is not None and any("amount" in df.columns for df in an.tables.values())
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.text_input("عمود الهدف لاختبار الفائدة (عمود ثنائي، أو label=column>pNN)",
                          value="is_large_claim=amount>p90" if has_amount else "", key="target")
            c2.selectbox("النموذج", ["stratified_copula", "gaussian_copula"], key="method",
                         help="stratified_copula: نموذج لكل قيمة من العمود الأكثر تأثيراً في الأعمدة الرقمية")
            c3.number_input("البذرة (seed)", min_value=0, max_value=10_000, value=0, step=1, key="seed",
                            help="تغيّر تقسيم بيانات الاختبار، وبالتالي النموذج المدرَّب.")
        st.divider()
        c1, c2 = st.columns([1, 2])
        c1.checkbox("اكتب النظير في قاعدة بيانات", key="write_db",
                    help="يُكتب النظير في قاعدة MySQL منفصلة، ولا يُكتب في المصدر أبداً.")
        c2.text_input("قاعدة الهدف", value="nazeer_dev", key="target_db", disabled=not st.session_state.get("write_db"))
        if an is not None:
            st.divider()
            _review_editor(an)


# ---------------------------------------------------------------- secondary tabs

def section_why() -> None:
    an = st.session_state["analysis"]
    st.header("ليش يشتغل؟", anchor=False)
    show('<p class="nz-lead">كل سبب جذري ← المكوّن الذي يعالجه ← رقم مقاس من بياناتك وتشغيلك الحالي.</p>')
    if an is None:
        st.info("حمّل بيانات العرض في تبويب «نَظير» أولاً؛ كل رقم هنا يُحسب مباشرة من بياناتك ومن آخر تشغيل.")
        return
    rows = ui.why_it_works(an, st.session_state["result"], st.session_state["golden"])
    out = ['<div class="nz-why-head"><div>السبب الجذري</div><div></div><div>مكوّن نَظير</div><div></div>'
           "<div>المقياس الحي</div></div>"]
    for r in rows:
        metric = (f'<div class="nz-mid">{ltr_numbers(r["metric"])}</div>' if r["metric"]
                  else '<div class="nz-mid" style="opacity:.5">—</div>')
        out.append(f'<div class="nz-why"><div class="nz-cell cause">{esc(r["cause"])}</div><div class="nz-arrow">←</div>'
                   f'<div class="nz-cell comp">{esc(r["component"])}</div><div class="nz-arrow">←</div>'
                   f'<div class="nz-cell metric {"" if r["metric"] else "pending"}">{metric}'
                   f'<div class="nz-sub">{ltr_numbers(r["detail"])}</div></div></div>')
    show("".join(out))
    show('<p class="nz-note">أرقام الكشف على بيانات العرض المولَّدة تُثبت تغطية الصيغ التي زرعناها، '
         "ولا تتنبأ بالأداء على نصوص حقيقية.</p>")


def section_try() -> None:
    from nazeer import detect

    st.header("جرّب نصّك", anchor=False)
    show('<p class="nz-lead">اكتب ملاحظة بالعربية فيها هوية أو جوال أو آيبان، بأرقام عربية أو بمسافات، وقارن.</p>')
    text = st.text_area("النص", value=TRY_EXAMPLE, key="try_text", height=120)
    if not text or not text.strip():
        return
    ner = _name_detector()
    naz = [Span("try", 0, "text", a, b, k, c, src) for a, b, k, c, src in detect.find_spans(text, ner)]
    base = [Span("try", 0, "text", a, b, k, c, src) for a, b, k, c, src in detect.baseline_find_spans(text)]
    base_marks, naz_marks = ui.note_marks(text, naz, base)
    c1, c2 = st.columns(2)
    c1.markdown(f'<h4 style="margin:.2rem 0 .4rem">أداة تقليدية · {len(base)}</h4>' + marked(text, base_marks),
                unsafe_allow_html=True)
    c2.markdown(f'<h4 class="nz-title-twin" style="margin:.2rem 0 .4rem">نَظير · {len(naz)}</h4>'
                + marked(text, naz_marks), unsafe_allow_html=True)
    key = os.environ.get(KEY_ENV, "").encode("utf-8") if len(os.environ.get(KEY_ENV, "")) >= 32 else DEMO_KEY
    masked_text = ui.mask_text(text, [(sp.start, sp.end, sp.type) for sp in naz], key)
    show('<h4 class="nz-title-twin" style="margin:1rem 0 .4rem">بعد الإخفاء</h4>'
         + marked(masked_text, ui.twin_marks(masked_text), "twin"))
    show('<p class="nz-note">معاينة فقط: لا يُحفظ النص ولا يُرسل لأي مكان.</p>')


# ---------------------------------------------------------------- main

def main() -> None:
    st.set_page_config(page_title="نَظير · Nazeer", page_icon="🛡️", layout="wide")
    _init()
    inject_css()
    header()
    tab_flow, tab_why, tab_try = st.tabs(["نَظير", "ليش يشتغل؟", "جرّب نصّك"])
    with tab_flow:
        ensure_analysis()
        if st.session_state["analysis"] is not None:
            _do_pending(st.session_state["analysis"])
        step = st.session_state["step"]
        if st.session_state["analysis"] is None:
            step = 1
        elif step == 4 and st.session_state["result"] is None:
            step = 3
        st.session_state["step"] = step
        stepper(step)
        if st.session_state["error"]:
            st.error(_md_safe(st.session_state["error"]))
        {1: step_data, 2: step_detect, 3: step_twin, 4: step_proof}[step]()
        st.write("")
        advanced()
    with tab_why:
        section_why()
    with tab_try:
        section_try()


main()
