"""Nazeer Streamlit UI (runs locally, inside the data owner's environment).

    $env:NAZEER_KEY = "<at least 32 random characters>"
    streamlit run nazeer\\app.py

Flow: load tables -> detection (with baseline comparison) -> run -> metrics -> download.
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
import zipfile  # noqa: E402
from collections import Counter  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from nazeer import pipeline  # noqa: E402
from nazeer.config import KeyConfigError, load_key  # noqa: E402
from nazeer.mysqlio import MySQLError  # noqa: E402
from nazeer.policy import load_policy  # noqa: E402
from nazeer.safe_log import configure_logging  # noqa: E402
from nazeer.tableio import load_csv_folder, read_csv  # noqa: E402
from nazeer.ui_logic import (ACTIONS, KINDS, TAGS, detection_frame, overrides_from_edits,  # noqa: E402
                             suggestion_frame, why_it_works)

log = logging.getLogger("nazeer.app")
ROOT = _HERE.parent
DEMO_DIR = Path(os.environ.get("NAZEER_DEMO_DIR", ROOT / "data" / "demo"))

TAG_COLORS = {"DIRECT_ID": "#f8d0d0", "QUASI_ID": "#fde3bd", "SENSITIVE": "#e6d7f5",
              "FREE_TEXT": "#d4e6fb", "NORMAL": "#ececec"}
SPAN_COLORS = {"SAUDI_ID": "#ffb3b3", "MOBILE": "#ffd59e", "IBAN": "#c9b6f2", "EMAIL": "#b7e4c7",
               "PERSON_NAME": "#a9d2f5"}


# ---------------------------------------------------------------- helpers

def _init() -> None:
    if "logging" not in st.session_state:
        configure_logging()
        st.session_state["logging"] = True
    for k in ("tables", "source", "golden_dir", "analysis", "result", "error", "applied_fix",
              "mysql_db", "mysql_schema", "mysql_written"):
        st.session_state.setdefault(k, None)
    st.session_state.setdefault("overrides", {})
    st.session_state.setdefault("ner_mode", "gazetteer")


def _reset_after_load() -> None:
    for k in ("analysis", "result", "error", "applied_fix", "mysql_written"):
        st.session_state[k] = None
    st.session_state["overrides"] = {}


def _guarded(fn, *args, **kwargs):
    """Run a step; on error show a generic message and log type + frames only (never values)."""
    st.session_state["error"] = None
    try:
        return fn(*args, **kwargs)
    except (KeyConfigError, MySQLError) as e:  # messages are credential- and value-free by construction
        st.session_state["error"] = str(e)
    except Exception as e:  # noqa: BLE001 - UI boundary
        log.error("UI step %s failed", getattr(fn, "__name__", "step"), exc_info=True)
        st.session_state["error"] = f"{type(e).__name__}: the step failed. Details are in the server log (values suppressed)."
    return None


@st.cache_resource(show_spinner="Loading the Arabic NER model (first time only)…")
def _camel_union():
    from nazeer.ner import get_name_detector

    return get_name_detector("union")


def _name_detector():
    if st.session_state.get("ner_mode") == "union":
        return _camel_union()
    return None  # gazetteer default


def load_demo() -> None:
    if not (DEMO_DIR / "customers.csv").exists():
        from data_gen import make_demo_data
        make_demo_data.main(["--seed", "42", "--n", "3000", "--out", str(DEMO_DIR)])
    st.session_state.update(tables=load_csv_folder(DEMO_DIR), source="demo dataset (generated, no real people)",
                            golden_dir=DEMO_DIR / "_golden")
    _reset_after_load()


def load_uploads(files) -> None:
    tables = {Path(f.name).stem: read_csv(f) for f in files}
    st.session_state.update(tables=tables, source=f"{len(tables)} uploaded CSV file(s)", golden_dir=None,
                            mysql_db=None, mysql_schema=None)
    _reset_after_load()


def load_mysql_source(database: str) -> None:
    from nazeer import mysqlio

    settings = mysqlio.load_settings()
    tables, schema = mysqlio.load_mysql(settings, database)
    st.session_state.update(tables=tables, source=f"MySQL database {database} (read-only)", golden_dir=None,
                            mysql_db=database, mysql_schema=schema)
    _reset_after_load()


def highlight(text: str, spans: list[tuple[int, int, str]]) -> str:
    out, last = [], 0
    for a, b, kind in sorted(spans):
        if a < last:
            continue
        out.append(html.escape(text[last:a]))
        out.append(f'<mark style="background:{SPAN_COLORS.get(kind, "#eee")};padding:0 2px;border-radius:3px" '
                   f'title="{kind}">{html.escape(text[a:b])}</mark>')
        last = b
    out.append(html.escape(text[last:]))
    return (f'<div dir="rtl" style="font-size:1.05rem;line-height:2;border:1px solid #ddd;border-radius:8px;'
            f'padding:10px 14px;background:#fff;color:#222">{"".join(out)}</div>')


def legend() -> str:
    return " ".join(f'<span style="background:{c};padding:1px 6px;border-radius:3px;margin-right:4px">{k}</span>'
                    for k, c in SPAN_COLORS.items())


def twin_zip(result: pipeline.RunResult) -> bytes:
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if not result.twin_withheld:
            for name, df in result.twin.items():
                z.writestr(f"twin/{name}.csv", df.to_csv(index=False, lineterminator="\n"))
        z.writestr("report.json", json.dumps(result.report, ensure_ascii=False, indent=2, default=str))
    return buf.getvalue()


# ---------------------------------------------------------------- sections

def section_input() -> None:
    st.header("1 · Load data")
    c1, c2, c3 = st.columns([1, 2, 2])
    with c1:
        if st.button("Use demo dataset", type="primary", key="demo"):
            _guarded(load_demo)
    with c3:
        with st.container(border=True):
            st.markdown("**Connect to MySQL** (read-only)")
            db = st.text_input("Source database", value="nazeer_prod_demo", key="mysql_source")
            st.caption("Credentials come from NAZEER_MYSQL_* or .env, never from this page.")
            if st.button("Connect", key="mysql_connect"):
                _guarded(load_mysql_source, db)
    with c2:
        files = st.file_uploader("…or upload CSV files (one table per file)", type="csv",
                                 accept_multiple_files=True, key="upload")
        if files and st.button("Load uploaded files", key="load_uploads"):
            _guarded(load_uploads, files)
    st.radio("Name detection in free text", ["gazetteer", "union"], key="ner_mode", horizontal=True,
             format_func=lambda m: {"gazetteer": "Fast (Arabic name lists)",
                                    "union": "Best recall (CamelBERT + name lists; ~0.1 s per note on CPU)"}[m])
    if st.session_state["tables"] is not None:
        st.caption(f"Loaded: {st.session_state['source']} — " + ", ".join(
            f"{n} ({len(df):,} rows × {df.shape[1]} cols)" for n, df in st.session_state["tables"].items()))


def section_detection() -> None:
    if st.session_state["tables"] is None:
        return
    if st.session_state["analysis"] is None:
        with st.spinner("Profiling and detecting personal data…"):
            schema = st.session_state["mysql_schema"]
            st.session_state["analysis"] = _guarded(
                lambda: pipeline.analyze(
                    st.session_state["tables"], st.session_state["source"], ner=_name_detector(),
                    db_fks=schema.foreign_keys if schema else None, db_pks=schema.primary_keys if schema else None))
    an: pipeline.Analysis | None = st.session_state["analysis"]
    if an is None:
        return
    st.header("2 · What Nazeer found")
    keys = [f"{n}: PK `{t.primary_key}`" for n, t in an.profile.tables.items()]
    fks = [f"`{f.child_table}.{f.child_column}` → `{f.parent_table}.{f.parent_column}`" for f in an.profile.foreign_keys]
    st.markdown("**Keys** — " + "; ".join(keys) + ("  \n**Relationships** — " + "; ".join(fks) if fks else ""))

    rows = [{"table": d.table, "column": d.column, "type": an.profile.column(d.table, d.column).dtype,
             "tag": d.tag, "identifier": d.kind or "", "confidence": round(d.score, 2),
             "needs review": "yes" if d.needs_review else "", "why": d.reason} for d in an.detections]
    df = pd.DataFrame(rows)
    st.dataframe(df.style.apply(lambda r: [f"background-color:{TAG_COLORS[r['tag']]}"] * len(r), axis=1),
                 hide_index=True, width="stretch")
    _review_editor(an)

    if an.spans or an.baseline_spans:
        st.subheader("Identifiers hidden in Arabic free text")
        naz, base = Counter(s.type for s in an.spans), Counter(s.type for s in an.baseline_spans)
        kinds = ["SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"]
        cols = st.columns(len(kinds) + 1)
        cols[0].metric("Baseline (generic regex)", f"{sum(base.values()):,}")
        cols[1].metric("Nazeer", f"{sum(naz.values()):,}", delta=f"{sum(naz.values()) - sum(base.values()):+,}")
        comp = pd.DataFrame({"identifier": kinds, "baseline found": [base[k] for k in kinds],
                             "Nazeer found": [naz[k] for k in kinds]})
        st.dataframe(comp, hide_index=True, width="content")
        golden = st.session_state["golden_dir"]
        if golden is not None and (golden / "golden_labels.csv").exists():
            scores = pipeline._golden_scores(an, golden)
            st.caption("Against the demo answer key (planted identifiers): "
                       f"Nazeer recall **{scores['nazeer']['overall_recall']:.1%}**, precision "
                       f"**{scores['nazeer']['overall_precision']:.1%}** · baseline recall "
                       f"**{scores['baseline']['overall_recall']:.1%}**, precision "
                       f"**{scores['baseline']['overall_precision']:.1%}**")
        _note_viewer(an)


def _note_viewer(an: pipeline.Analysis) -> None:
    per_row = Counter((s.table, s.column, s.row) for s in an.spans)
    base_row = Counter((s.table, s.column, s.row) for s in an.baseline_spans)
    ranked = sorted(per_row, key=lambda k: (-(per_row[k] - base_row.get(k, 0)), k))[:50]
    if not ranked:
        return
    choice = st.selectbox("Compare on one note (notes where Nazeer finds the most that the baseline misses):",
                          ranked, format_func=lambda k: f"{k[0]}.{k[1]} row {k[2]} — Nazeer {per_row[k]}, baseline {base_row.get(k, 0)}",
                          key="note_pick")
    t, c, r = choice
    text = an.tables[t][c].iat[r]
    st.markdown(legend(), unsafe_allow_html=True)
    left, right = st.columns(2)
    left.markdown("**Baseline**")
    left.markdown(highlight(text, [(s.start, s.end, s.type) for s in an.baseline_spans if (s.table, s.column, s.row) == choice]),
                  unsafe_allow_html=True)
    right.markdown("**Nazeer**")
    right.markdown(highlight(text, [(s.start, s.end, s.type) for s in an.spans if (s.table, s.column, s.row) == choice]),
                   unsafe_allow_html=True)


def _review_editor(an: pipeline.Analysis) -> None:
    pending = sum(d.needs_review for d in an.detections)
    label = "Review and override detections" + (f" — {pending} column(s) need review" if pending else "")
    with st.expander(label, expanded=bool(pending)):
        st.caption("Change a column's tag, identifier type or action, or tick *reviewed* to confirm it. "
                   "Every change is recorded in the report as human-reviewed. The leak scan still checks "
                   "every identifier Nazeer detected, whatever you change here.")
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
            st.info(f"{len(overrides)} human override(s) will be applied and recorded: " + ", ".join(overrides))


def _kanon_panel(rep: dict) -> None:
    for table, k in rep.get("k_anonymity", {}).items():
        st.subheader(f"k-anonymity · {table}")
        st.caption(f"Quasi-identifiers: {', '.join(k['quasi_columns'])}. Minimum k: {k['k_min']}.")
        c = st.columns(3)
        c[0].metric("k before fix", k["k_before"])
        c[1].metric("k now", k["k_after"], delta=None if k["k_after"] == k["k_before"] else f"{k['k_after'] - k['k_before']:+d}")
        c[2].metric("Rows in classes below k (before)", k["rows_in_small_classes_before"])
        if k.get("applied_fix"):
            f = k["applied_fix"]
            st.success(f"Applied fix **{f['name']}**: {f['description']} — k {f['k_before']} → {f['k_after']}, "
                       f"{f['rows_affected']} row(s) affected. The original FAIL stays in the report.")
        elif k["suggestions"]:
            st.warning(f"k = {k['k_before']} is below {k['k_min']}. Choose a fix (nothing is applied automatically):")
            st.dataframe(suggestion_frame(k), hide_index=True, width="stretch")
            names = [f["name"] for f in k["suggestions"]]
            pick = st.selectbox("Fix to apply", names, key="fix_pick")
            if st.button("Apply fix and re-run", key="apply_fix"):
                an = st.session_state["analysis"]
                with st.spinner("Re-running with the chosen fix…"):
                    st.session_state["result"] = _guarded(
                        lambda: pipeline.run_masked(an, load_policy(pipeline.DEFAULT_POLICY), load_key(),
                                                    st.session_state["overrides"], apply_fix=pick,
                                                    golden_dir=st.session_state["golden_dir"]))
                    st.session_state["applied_fix"] = pick
                st.rerun()


def _write_to_mysql(target_db: str) -> None:
    from nazeer import mysqlio

    mysqlio.check_target(st.session_state["mysql_db"], target_db)
    settings = mysqlio.load_settings()
    entry = pipeline.write_twin_to_mysql(st.session_state["result"], st.session_state["analysis"], settings,
                                         target_db, st.session_state["mysql_db"], st.session_state["mysql_schema"])
    st.session_state["mysql_written"] = entry


def section_run() -> None:
    an = st.session_state["analysis"]
    if an is None:
        return
    st.header("3 · Generate the twin")
    mode = st.radio("Mode", ["masked", "synthetic"], horizontal=True, key="mode",
                    format_func=lambda m: {"masked": "Masked twin (5a) — same rows, pseudonymized, for testing",
                                           "synthetic": "Synthetic twin (5b) — new rows, for analytics/AI"}[m])
    target, method = None, "stratified_copula"
    if mode == "synthetic":
        has_amount = any("amount" in df.columns for df in an.tables.values())
        c1, c2 = st.columns([2, 1])
        target = c1.text_input("Utility test target (binary column, or `label=column>pNN`)",
                               value="is_large_claim=amount>p90" if has_amount else "", key="target") or None
        method = c2.selectbox("Synthesizer", ["stratified_copula", "gaussian_copula"], key="method",
                              help="stratified_copula: one Gaussian copula per value of the column that drives the "
                                   "numeric columns most (chosen automatically)")
        st.caption("20% of the data is held out before training and is used only to test utility and privacy.")
    c1, c2 = st.columns([1, 2])
    write_db = c1.checkbox("Write twin to database", key="write_db",
                           help="Also write the twin to a SEPARATE MySQL database (never the source).")
    target_db = c2.text_input("Target database", value="nazeer_dev", key="target_db", disabled=not write_db)
    if st.button("Run Nazeer", type="primary", key="run"):
        with st.spinner("Transforming, scanning for leaks, measuring… (synthetic mode takes about a minute)"):
            policy = load_policy(pipeline.DEFAULT_POLICY)
            if mode == "masked":
                st.session_state["result"] = _guarded(
                    lambda: pipeline.run_masked(an, policy, load_key(), st.session_state["overrides"],
                                                golden_dir=st.session_state["golden_dir"]))
                st.session_state["applied_fix"] = None
            else:
                st.session_state["result"] = _guarded(
                    lambda: pipeline.run_synthetic(an, policy, st.session_state["overrides"], target=target,
                                                   method=method, golden_dir=st.session_state["golden_dir"]))
            if write_db and st.session_state["result"] is not None:
                _guarded(_write_to_mysql, target_db)


def _metric_panels(rep: dict) -> None:
    if rep["mode"] == "synthetic":
        st.subheader("Utility · fidelity · privacy")
        u, d, f = rep.get("utility", {}), rep["privacy"]["dcr"], rep.get("fidelity", {})
        c = st.columns(4)
        if u.get("models"):
            best = max(u["models"].values(), key=lambda m: m["real"]["auc"] or 0)
            c[0].metric("AUC trained on real", f"{best['real']['auc']:.3f}")
            c[1].metric("AUC trained on twin", f"{best['twin']['auc']:.3f}", delta=f"{-best['auc_drop']:+.3f}")
        c[2].metric("DCR twin→train (median)", f"{d['median_dcr_twin_to_train']:.4f}",
                    help=f"holdout→train: {d['median_dcr_holdout_to_train']:.4f}; twin must not be closer")
        c[3].metric("SDMetrics quality", f"{f.get('sdmetrics_quality_score') or 0:.1%}")
        if u.get("models"):
            st.dataframe(pd.DataFrame([{"model": n, "AUC real": m["real"]["auc"], "AUC twin": m["twin"]["auc"],
                                        "drop": m["auc_drop"], "F1 real": m["real"]["f1"], "F1 twin": m["twin"]["f1"]}
                                       for n, m in u["models"].items()]), hide_index=True, width="content")
        cols = f.get("columns", {})
        if cols:
            st.dataframe(pd.DataFrame([{"column": k, "metric": v["metric"], "distance (0 = identical)": v["value"]}
                                       for k, v in cols.items()]), hide_index=True, width="content")
    else:
        leak = rep["leak_scan"]
        c = st.columns(4)
        c[0].metric("Identifier leaks in twin", sum(leak["leaked_by_kind"].values()))
        c[1].metric("Cells scanned", f"{leak['cells_scanned']:,}")
        c[2].metric("Spans replaced in text", f"{sum(rep['free_text'].get('spans_replaced_by_type', {}).values()):,}")
        k = next(iter(rep.get("k_anonymity", {}).values()), None)
        if k:
            c[3].metric("k-anonymity", k["k_after"], delta=None if k["k_after"] == k["k_before"] else
                        f"{k['k_after'] - k['k_before']:+d} after fix")


def section_results() -> None:
    res: pipeline.RunResult | None = st.session_state["result"]
    if res is None:
        return
    rep = res.report
    st.header("4 · Evidence")
    (st.success if rep["verdict"] == "PASS" else st.error)(
        f"Verdict: **{rep['verdict']}**" + (f" — failed: {', '.join(rep['failed_checks'])}" if rep["failed_checks"] else ""))
    checks = pd.DataFrame([{"check": c["name"], "status": c["status"], "blocks verdict": "yes" if c["blocking"] else "",
                            "detail": c["detail"]} for c in rep["checks"]])
    colors = {"PASS": "#d3f2d9", "FAIL": "#f8d0d0", "INFO": "#eef2f7", "NOT_RUN": "#ececec"}
    st.dataframe(checks.style.apply(lambda r: [f"background-color:{colors[r['status']]}"] * len(r), axis=1),
                 hide_index=True, width="stretch")

    if res.twin_withheld:
        st.warning("The leak scan failed, so the twin is withheld. Only the report can be downloaded.")
    else:
        st.subheader("Original vs twin")
        table = st.selectbox("Table", list(res.twin), key="cmp_table")
        n = st.slider("Rows", 5, 50, 10, key="cmp_rows")
        left, right = st.columns(2)
        originals = res.extras.get("originals", {})
        original = originals.get(table, st.session_state["analysis"].tables.get(table))
        left.markdown("**Original** (stays here)" if table not in originals else
                      "**Original training rows** (joined view; stays here)")
        left.dataframe(original.head(n), hide_index=True, width="stretch")
        right.markdown("**Twin**")
        right.dataframe(res.twin[table].head(n), hide_index=True, width="stretch")

    written = rep.get("mysql_output")
    if written:
        if written.get("written"):
            leak = written["leak_scan_of_target"]
            (st.success if leak["verdict"] == "PASS" and written["row_counts_match"] else st.error)(
                f"Twin written to MySQL database **{written['target_database']}** — read back and leak-scanned: "
                f"{leak['verdict']} ({sum(leak['leaked_by_kind'].values())} identifiers in {leak['cells_scanned']:,} cells).")
        else:
            st.warning(written.get("note", "twin not written"))
    _metric_panels(rep)
    if rep["mode"] == "masked":
        _kanon_panel(rep)
    st.download_button("Download twin + report (zip)" if not res.twin_withheld else "Download report (zip)",
                       data=twin_zip(res), file_name=f"nazeer-{res.run_id}.zip", mime="application/zip", key="dl")
    with st.expander("Full report (JSON)"):
        st.json(rep, expanded=False)
    with st.expander("Known limitations"):
        for line in rep["limitations"]:
            st.markdown(f"- {line}")


def section_why() -> None:
    an: pipeline.Analysis | None = st.session_state["analysis"]
    st.subheader("Why it works: from root cause to measured result")
    if an is None:
        st.info("Load data in the Nazeer tab first; every number below is computed live from your data and your run.")
        return
    golden = st.session_state["golden_dir"]
    scores = pipeline._golden_scores(an, golden) if golden is not None else None
    table = why_it_works(an, st.session_state["result"], scores)
    st.table(table)
    st.caption("Each metric comes from the data loaded in this session and the most recent run. "
               "Detection numbers on generated demo data show that the planted formats are covered; "
               "they do not predict performance on real production text.")


def main() -> None:
    st.set_page_config(page_title="Nazeer · نظير", page_icon="🛡️", layout="wide")
    _init()
    st.title("Nazeer · نَظير")
    st.caption("Saudi-aware masked & synthetic data — runs locally; data never leaves this machine.")
    tab_run, tab_why = st.tabs(["Nazeer", "Why it works"])
    with tab_run:
        section_input()
        section_detection()
        section_run()
        if st.session_state["error"]:
            st.error(st.session_state["error"])
        section_results()
    with tab_why:
        section_why()


main()
