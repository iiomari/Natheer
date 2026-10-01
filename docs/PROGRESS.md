# Nazeer — Progress log

Source of truth for the design: `docs/PLAN.md` (the approved plan, verbatim).
This file is updated after every milestone so a new session can resume from it alone.

## Status

| Milestone | Status | Commit |
|---|---|---|
| M0 Setup + dependency verification | done | f7abbd5 |
| M1 saudi_ids + normalization | done | f338cbe |
| M2 Demo data + golden labels | done | 810dc40 |
| M3 Profile + detection + baseline | done | c20dbeb |
| M4 Policy + transform | done | 29a4efa |
| M5 Evaluation + report + k-anon backend | done | 174da99 |
| M6a Minimal Streamlit flow | done | 8a2edc4 |
| M7 Synthetic 5b + fidelity + TSTR + DCR | done (code + tests); committed under "WIP: pause", no separate M7 commit | WIP: pause |
| R1 DCR robustness (5 seeds, per stratum, min stratum fallback) | done | 2126e4c |
| M6b UI polish + overrides + k-anon apply | done | bf9106d |
| MySQL input + output (replaces PostgreSQL) | code + unit tests done; **live MySQL steps waiting for credentials** | 9b23043 |
| Independent evaluation harness (human-written notes) | done; **waiting for teammates' notes** | e430dc0 |
| "Why it works" tab | done | b27683d |
| Arabic NER (CamelBERT + gazetteer fallback) | done | 04a84ae |
| Final deliverables (README ar/en, demo runs, internal demo script) | done | e76aef2 |
| UI redesign for clarity (presentation only) | done | (this commit) |
| HMA multi-table synthesis | **out of scope for the hackathon** | — |
| PDF report | **out of scope for the hackathon** | — |

## Setup notes

- `docs/reference.html` (the JS prototype): **not found**. `$HOME\Downloads` has no
  `nazeer-prototype.html`, and no file matching "nazeer" or "prototype" exists in Downloads
  or on the Desktop. Work continues from `docs/PLAN.md` alone.
- Deadline and team size were never supplied (placeholders in the approval), so the cut line
  in the milestone table is not marked. The user asked for all milestones to be built anyway.

## Environment

```powershell
cd $HOME\Desktop\nazeer
.\.venv\Scripts\Activate.ps1
python -m pytest
```
Python 3.11.9 (Microsoft Store build), venv at `.venv`. Global site packages (pandas 3,
torch 2.2) are incompatible, so always use the venv.

## Deviations from the plan

(Each entry: what, why, and impact.)

1. **M0: SDV has no seed parameter.** It seeds itself internally, so samples are identical
   across fits. The `Synthesizer.sample(seed=...)` argument is recorded, but the SDV adapter
   cannot honor it. The report states "seed: fixed by SDV".
2. **M0: copulas and rdt are BUSL-1.1 too**, not only sdv and ctgan. A future replacement
   behind the `Synthesizer` protocol must use scipy/numpy directly.
3. **M1: the mobile validator also accepts `009665…`.** The spec lists only `05`, `+9665` and
   `9665`, but the `00966` international prefix is common in Saudi text.
4. **M1: normalization also removes no-break and thin spaces, Unicode dashes, the Arabic
   decimal and thousands separators, and bidi marks (LRM/RLM/ALM) between digits.** These
   appear in Arabic text around numbers. A run of more than 3 separator characters splits
   the number.

5. **M2: added `saudi_ids.is_valid(kind, raw)` and `flatten(raw)`.** `canonical("MOBILE")`
   is the 9-digit national number (the HMAC input) and is intentionally not a valid
   display format, so raw spans need a separate "validate any spelling" entry point.
6. **M2: extra demo outputs.** Besides `golden_labels.csv`, the generator writes
   `hard_negatives.csv` (look-alike IDs, other numbers, name-like words such as "أمل")
   for false-positive counting, and `golden_columns.csv` (expected column tags) for the
   column-level detector test.
7. **M3: `types.py` → `models.py` and `io.py` → `tableio.py`.** `streamlit run nazeerpp.py`
   puts `nazeer\` on `sys.path`, where these names would shadow the stdlib `types` and `io`
   modules. This is the same reason `profile.py` became `profiling.py`.
8. **M3: digit candidates are cut at original group boundaries** (gaps in the offset map)
   instead of only using the spec regex `(?<!\d)[12]\d{9}(?!\d)`. This finds an ID glued to a
   neighbouring number by a space ("12 1110704341"), which the plain regex misses after
   normalization merges them. The validator still gates every candidate.
9. **M3: name rules beyond the plain gazetteer.**
   - About 35 first names that are also everyday words (أمل, وعد, ندى, سالم, عادل, …) count
     only with a following family name or a person cue (title, role or kinship word) in the
     same sentence.
   - Raw function words that normalize into names (على→علي) are stopwords.
   - A clitic prefix (و/ب/ل/ف) is stripped when the remainder is a name.
10. **M3: the "needs review" band (0.4–0.7) is tagged DIRECT_ID with `needs_review=True`.**
    Unreviewed borderline columns are therefore pseudonymized (the safe default) until a
    human clears them.
11. **M3: QUASI_ID and SENSITIVE tags come from column-name hints only** (age/city/gender/…
    and amount/diagnosis/claim_type/…). The spec gives no value-based rule for these.
12. **M3: `evaluate.score_detection` was built in M3**, because the M3 test needs it.
    Matching rule: a golden span counts as found when a predicted span of the same type
    overlaps it. Exact-offset matches are counted separately.
13. **M4: name pseudonyms are many-to-one by design.** First and family names are mapped per
    token from small gazetteers (146/130/120 names), so uniqueness cannot be enforced. The
    only rule is that a token never maps to itself, which guarantees no row keeps its own
    full name (the agreed name leak rule). IDs, mobiles, IBANs and emails are injective, and
    their fakes never equal **any** original value of their kind.
14. **M4: the HMAC message is `f"{kind}:{canonical}"`** as specified, and `f"{kind}:{canonical}:{n}"`
    for the n-th rehash. Canonical forms: digits-only ID, 9-digit national mobile number,
    upper-case IBAN, lower-case email, `normalize_name` per name token.
15. **M4: `drop` was added as a policy action** (unused by default), for columns a reviewer
    wants removed entirely.
16. **M5: demo golden files moved to `data\demo\_golden\`.** The table loader reads every
    `*.csv` in the input folder, so the answer key must not sit next to the tables. The
    pipeline picks up `<csv>\_golden` automatically, for the demo only.
17. **M5: if the leak scan fails, the twin is withheld.** Only `report.json` and the log are
    written. This is stricter than "the run fails", and it was chosen so a leaking twin can
    never be picked up by mistake.
18. **M5: checks carry a `blocking` flag.** "k-anonymity before fix" is recorded as a
    non-blocking FAIL, so the original failure stays visible after the user applies a fix.
    The verdict depends only on blocking checks.
19. **M5: the leak scan's exhaustive pass** checks every 10-digit window (IDs), every
    `05…`/`9665…` window (mobiles), every 22-digit window (IBANs) and every email in every
    normalized cell. It is independent of the detector.
20. **M5: `jsonschema==4.26.0` was added to `requirements.txt`** for report schema validation.
    It was already installed as a Streamlit dependency.
21. **M5: k-anonymity is computed on the twin after policy generalization** (age in 10-year
    bins). Suggestions combine `widen_<col>`, `region_<col>` and `suppress`, and are ranked
    by reaching k_min first, then fewest rows affected, then fewest steps.
22. **M6a: `app.py` removes its own folder from `sys.path`** and imports the package from
    the repo root. `NAZEER_DEMO_DIR` (env) can point the "Use demo dataset" button at
    another folder; the tests use this.
23. **M6a: the key is only read from `NAZEER_KEY`; the UI has no key input field.** If the
    variable is missing, the UI shows the PowerShell command to set it.
24. **M7: single-table synthesis runs on a flat "analytics view".** The view is the largest
    child table joined with its parents, plus a generic derived column `prior_<child>` (earlier
    rows of the same parent, ordered by the first date column). The synthetic twin is one
    table, `claims_synthetic`. A true multi-table twin is M8 (HMA).
25. **M7: the default synthesizer is a stratified Gaussian copula, not a plain one.**
    - Plain `GaussianCopulaSynthesizer` gave a **TSTR AUC drop of 0.344**. CTGAN (150 epochs,
      262 s) gave **0.411**. Both FAIL the 0.05 limit, because neither captures "amount
      depends on which claim type".
    - `SdvStratifiedCopula` fits one SDV Gaussian copula per value of the categorical column
      with the highest mean η² against the numeric columns. This is chosen automatically, and
      on the demo it picked `claim_type` (η² = 0.849 with amount).
    - Strata under 50 rows are merged, and it falls back to a single copula when no column has
      η² ≥ 0.1.
    - The threshold was **not** changed. `--synthesizer gaussian_copula` still runs the plain
      model for comparison.
26. **M7: the `Synthesizer` protocol takes our own `SynthSchema`**, not the plan's
    `(prof, exclude)`. The caller applies exclusions first, so an adapter never sees
    identifiers, and a non-SDV adapter needs no Nazeer profiling types. `sample(scale, seed)`
    keeps the seed argument, but SDV adapters ignore it (see deviation 1).
27. **M7: high-cardinality text columns** (unique ratio > 0.5, not identifiers) are not
    modelled, because sampling them would copy real values. They are left empty in the twin
    and listed in the report.
28. **M7: DCR "rows at distance zero" uses a 1e-6 tolerance.** sklearn's Euclidean distance
    returns about 1e-8 for identical rows. A test (memorizing synthesizer) found this.

### Scope change (user, 2026-10-01): applies to all remaining work
29. **New order of the remaining work:**
    1. DCR robustness check
    2. M6b
    3. MySQL input and output
    4. Independent evaluation harness for human-written notes
    5. "Why it works" tab
    6. Arabic NER
    7. Final deliverables
30. **Dropped: HMA multi-table synthesis and the PDF report** are out of scope for the
    hackathon. The `SdvMultiTable` adapter already in `synth.py` stays as an unused seam,
    and `report.py` writes JSON only.
31. **PostgreSQL → MySQL.**
    - Driver: SQLAlchemy + PyMySQL, always with `charset=utf8mb4`.
    - FKs are read from `information_schema.KEY_COLUMN_USAGE`.
    - The source is read-only (SELECT only).
    - Optional output goes to a *separate* database with the same PKs/FKs, `utf8mb4` and
      `utf8mb4_unicode_ci`. The run is refused if target == source.
    - `python -m data_gen.load_mysql` creates `nazeer_prod_demo`.
    - Credentials come from `NAZEER_MYSQL_*` environment variables or a local `.env`
      (python-dotenv). Real environment variables win. `.env` is gitignored, and
      `.env.example` is committed.
    - If the password is still `CHANGE_ME`, the MySQL steps are marked "waiting for
      credentials" and their tests are skipped with a reason.
32. **Judging criteria and weights are internal only.** They appear only in
    `docs/internal/DEMO_SCRIPT.md` (headed "Internal team document — do not share."). They
    never appear in the app, the README, reports or any judge-facing file. Metric values may
    be shown anywhere. There is no business or commercial section anywhere.
33. **New: independent evaluation harness.** Teammates write `data/human_notes.csv`
    (`author,note`, identifiers wrapped as `⟦TYPE:value⟧`) without seeing the generator.
    `python -m nazeer.eval_human` scores Nazeer vs baseline and lists misses by type and
    position only. `data/human_notes.csv` is gitignored: hand-written notes could accidentally
    contain a real identifier.
34. **New: "Why it works" tab.** It shows only root cause → Nazeer component → live metric.
35. **R1: minimum stratum size is 100 training rows (was 50 with a merged "other" copula).**
    A smaller stratum gets no copula of its own. Its rows are drawn from a **pooled** copula
    fitted on all training rows and sampled conditionally on the stratum value
    (`sample_from_conditions`). On the full demo one stratum (97 rows) now uses the pooled
    fallback.
36. **R1: the DCR PASS rule is unchanged.** Robustness and per-stratum DCR are added as
    non-blocking INFO checks (`--dcr-seeds 5` by default in the CLI). Each seed is a different
    holdout split, and therefore a different fit.
37. **R1: Hypothesis timing health checks are off for the offset-map property test.** Under
    machine load, input generation took 1.6 s and tripped `too_slow`. The property assertions
    are unchanged.
38. **M6b: override logic lives in `nazeer/ui_logic.py`** (pure functions) so it can be unit-tested
    without Streamlit. The UI offers tag, identifier type, action (`policy` / `keep` /
    `pseudonymize` / `drop`) and a "reviewed" tick. `generalize` is not offered in the editor
    because it needs parameters; it stays a policy-file action.
39. **M6b: overrides cannot hide identifiers from the leak scan.** The leak scan searches for
    every identifier detected at analysis time, including in columns a reviewer un-tagged.
    Un-tagging the notes column therefore makes the run FAIL and withholds the twin (tested).
    Columns newly tagged FREE_TEXT by a reviewer are scanned at run time.
40. **MySQL: `cryptography==50.0.2` added.** The local server is MySQL 9.1.0, which removed
    `mysql_native_password`. PyMySQL needs `cryptography` for `caching_sha2_password` over
    plain TCP. `requirements-postgres.txt` was deleted; SQLAlchemy, PyMySQL, python-dotenv
    and cryptography are now pinned in `requirements.txt`.
41. **MySQL: Nazeer's own sessions use `sql_mode=STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION`.**
    The local server's `my.ini` sets `sql_mode=""` (non-strict), which silently truncates or
    coerces bad values. The server setting is **not** changed. Strictness is per session, so a
    mismatch fails loudly. The user was told.
42. **MySQL: the source is opened as `SET SESSION TRANSACTION READ ONLY`**, so the server
    itself rejects writes, on top of issuing SELECT only.
43. **MySQL: target column types keep the source type only when every twin value fits it**
    (generalized ages like "30-39" no longer fit INT and become VARCHAR). Tables are recreated
    in the target on every run (`DROP TABLE IF EXISTS` inside the target database only).
44. **MySQL: an empty password is accepted**, because WAMP's default root account has none.
    Only the `CHANGE_ME` placeholder means "waiting for credentials".
45. **MySQL: what lands in the target is verified.** After writing, the twin is read back from
    the target database and leak-scanned again. A blocking check,
    `leak_scan_target_database`, also compares row counts. A withheld twin is never written.
46. **MySQL in the UI: credentials are never entered on the page.** Only the database names
    are typed in the UI. `MySQLError` messages are shown verbatim, because they contain no
    credentials or values by construction.
47. **Evaluation harness: recall is reported twice**, on all marked identifiers and on
    format-valid ones only. Hand-invented 10-digit "IDs" usually fail the national-ID
    checksum, and Nazeer rejects those by design (that is what separates an ID from an invoice
    number). `--make-ids N` prints valid fake identifiers for writers to paste. Names have no
    official format and always count in both.
48. **Evaluation harness: an `EMAIL` marker was added** (the request listed ID, MOBILE, IBAN
    and NAME). Malformed markup (unknown type, empty, nested, unbalanced) is reported per row
    and the row is skipped. It never crashes the run.
49. **`ner.get_name_detector("auto" | "gazetteer" | "camel")`** was added ahead of the NER step.
    For now "auto" falls back to the gazetteer, because CamelBERT is not installed yet.
50. **"Why it works": the "runs locally" row reports checkable configuration facts**
    (Hugging Face offline mode and telemetry, Streamlit usage statistics, server bind
    address) instead of an unverifiable "no network calls" claim.
51. **The "internal only" rule is enforced by a test.** `tests/test_internal_only.py` fails if
    any judge-facing file (README, app, ui_logic, report, pipeline, notes guide, template) or
    any generated `out/**/report.json` mentions criteria, judging, weights or a rubric
    (English and Arabic).
52. **NER: the default name detector stays the gazetteer.** CamelBERT is offered as
    "union" (CamelBERT + gazetteer).
    - Measured on CPU: about 215–300 ms per note, so the union would need about 26 minutes for
      the 7,160 demo notes.
    - The union is the default only in the human-notes harness (`auto`), which has few notes.
    - Pipeline `--ner`: gazetteer | union | camel | auto. The UI offers "Fast" (gazetteer) and
      "Best recall" (union).
    - The model loads strictly from the local cache, pinned to revision `54e2905e…`. A
      900-second time budget per batch run falls back to the gazetteer and records this in
      `name_detector.stats`.
53. **NER: name spans that overlap a digit/IBAN/email span are dropped**, so a model can never
    label part of a number as a name.
54. **NER caveat: the demo is biased toward the gazetteer.** The demo generator draws names from
    the same lists the gazetteer uses, so the gazetteer's recall on the demo is optimistic.
    The hand-written notes are the fair comparison.

### UI redesign (user, 2026-10-01): presentation layer only
55. **Preset demo key.** "تحميل بيانات العرض" also enables a public, hard-coded demo key, so the demo needs
    nothing typed. It is used **only** for the generated demo dataset and **only** when `NAZEER_KEY` is not
    set; uploads and MySQL still require `NAZEER_KEY` (tested). When it is used, the app writes
    `key.source = "preset demo key (generated demo dataset only; public, not a secret)"` into the report, so
    the report stays truthful. This is the only change to report content, and it happens in the UI.
56. **"للمراجعة" (needs review) is a display label for span confidence ≤ 0.7**: a lone first name with no
    family name or cue, or an ID next to an invoice-like word. The pipeline still replaces every span at or
    above `min_span_confidence` (0.5). Nothing about detection changed.
57. **Two of the four proof cards are readouts, not new report checks.** "صلاحية البدائل" is PASS when 100% of
    fake identifiers pass the official validators, and "سلامة الروابط" is PASS at 0 orphan foreign keys. Both
    reuse `ui_logic.fake_validity` / `referential_integrity`, which the "Why it works" tab already showed. The
    verdict banner still comes from the report's blocking checks only.
58. **`tests/test_app.py` was adapted to the new navigation.** Every existing test keeps its name and its
    behavioural assertions. Only the click path changed (next → next → generate) and English label
    assertions became Arabic. `test_missing_key_shows_message_not_traceback` now simulates non-demo data,
    because demo mode intentionally has a key.
59. **Slow actions use "pending" flags instead of `st.rerun()`.** A test found that `st.rerun()` in the middle
    of a script run dropped the state of widgets not yet rendered in that run (the twin mode silently
    reset to masked).
60. **Numbers use `unicode-bidi: isolate-override`, not just an isolate.** Found on screen: inside an LTR
    isolate, a space between two Arabic-Indic digit groups still resolves right-to-left (bidi rule N1), so
    `٠٥٠ ٣٣١ ٨٨٤٢` showed as `٨٨٤٢ ٣٣١ ٠٥٠`. Text containing Arabic letters keeps a plain isolate.
61. **Step 3's sentence "نفس الأعداد والمجاميع والروابط — بدون عميل حقيقي."** is the requested wording. It is
    shown only when the live row-count, total and orphan-link checks all hold. The PDPL caveat (a masked
    twin is still likely personal data) is unchanged in the report's limitations.

## Milestone log

### M2: Demo data + golden labels
- `python -m data_gen.make_demo_data --seed 42 --n 3000` gives 3,000 customers and 7,160
  claims. The output is byte-identical across two runs, for all 5 files.
- Golden labels: 15,989 planted identifiers in notes (PERSON_NAME 6,512, MOBILE 3,945,
  SAUDI_ID 3,044, IBAN 1,523, EMAIL 965), in 5,326 of 7,160 notes.
- Hard negatives: 6,756 (LOOKALIKE_ID 2,787, NUMBER 2,862, NAME_WORD 1,107).
- Digit rendering: ASCII 50%, Arabic-Indic 40%, Persian 10%. Separators: none 50%,
  space 32%, hyphen 18%. Mobiles appear as 05 / +966 / 966 / 00966.
- Customer columns are messy on purpose: 3% of national IDs stored in Arabic-Indic, and
  15% of mobiles stored as +966/966.
- Notes reuse the claimant's own name, ID and mobile, so M4 can test column↔text consistency.
- Signal: amount = base(type) × age factor × (1 + 0.25·prior claims) × lognormal noise.
  P90 = 14,916 SAR.
- The generator self-checks: every golden span passes `is_valid`, and every look-alike
  fails both the ID and mobile validators.
- Tests: 93 passed (6 new demo-data tests).

### M3: Profile + detection + baseline
- Profiling on the demo finds PKs `customers.customer_id` and `claims.claim_id`, and the FK
  `claims.customer_id → customers.customer_id` (containment 1.0). Types: notes=free_text,
  claim_date=date, amount/age=numeric, gender/city=categorical.
- Column tags match `golden_columns.csv` for all 13 columns. Identifier columns are tagged
  DIRECT_ID with no review flag.
- Free-text detection on the full demo (seed 42, 3,000 customers, 7,160 notes, 15,989 planted
  identifiers). Command: `python scripts\score_detection.py`

  | type | gold | Nazeer recall | Nazeer precision | baseline recall | baseline precision |
  |---|---|---|---|---|---|
  | SAUDI_ID | 3,044 | 1.000 | 1.000 | 0.265 | 0.533 |
  | MOBILE | 3,945 | 1.000 | 1.000 | 0.141 | 1.000 |
  | IBAN | 1,523 | 1.000 | 1.000 | 0.431 | 1.000 |
  | EMAIL | 965 | 1.000 | 1.000 | 1.000 | 1.000 |
  | PERSON_NAME | 6,512 | 0.981 | 1.000 | 0.000 | – |
  | **overall** | 15,989 | **0.992** | **1.000** | **0.187** | **0.809** |

  Hard negatives hit: Nazeer 0 / 6,756, baseline 707 / 6,756 (mostly look-alike invoice numbers).
- **Honesty caveat:** our own generator produced these notes, and it uses the same formats the
  detector knows. Recall of 1.000 on structured IDs shows that every planted format is covered.
  It does not predict recall on real production text, which will contain formats we did not
  plant. Name recall (0.981) misses ambiguous names written without a cue (for example
  "طلب أمل تحديث…"). This is a deliberate precision/recall trade-off.
- Two real bugs were found by tests and fixed generally: "على" was read as the name "علي", and
  a role cue at the end of one sentence carried over to the next sentence ("…المستفيد. وعد…").
- Tests: 112 passed.

### M4: Policy + transform
- `config/policy.yaml` is the approved example policy. Resolution order: override → identifier
  kind → primary/foreign key → column-name rule → free_text → default. Rules naming absent
  columns (`birth_date`, `nationality`) are reported as inactive.
- `Pseudonymizer` implements the keyed HMAC, the forbidden-original and collision rehash,
  sorted `prepare()`, per-token names and `render_like`.
- Tests (33 in `test_transform.py`) cover:
  - determinism ×100 and across 2 subprocesses with different `PYTHONHASHSEED`;
  - a different key giving a different fake;
  - fakes that validate and differ from the original;
  - the citizen/resident digit being kept;
  - name gender and family slot kept, and a first name alone matching the full-name token;
  - all mobile spellings sharing one fake;
  - format preservation (Arabic-Indic/Persian/ASCII, spaces/hyphens, `+966`/`00966`, IBAN groups and case);
  - end-to-start span replacement;
  - collision rehash and the forbidden-original rule;
  - order-independent `prepare`;
  - age and month generalization;
  - referential integrity on demo data (FK ⊆ PK, same join size and per-type counts);
  - keys remapped;
  - direct-ID columns fully replaced;
  - the claimant's ID in notes mapping to the same fake as in the customers column;
  - policy override precedence.
- Tests: 145 passed.

### M5: Evaluation + report + k-anon backend
Commands:
- `python -m nazeer.pipeline --csv data\demo --mode masked --out out\masked` (no fix applied)
- the same command with `--apply-fix auto` (auto fix)

Results on the full demo (3,000 customers, 7,160 claims):
- **Leak scan: PASS.** 0 original identifiers in 63,960 twin cells (detector and exhaustive
  passes), and 0 rows keeping their original full name.
- **Exact copies: 0.**
- 15,865 free-text spans replaced (SAUDI_ID 3,044, MOBILE 3,945, IBAN 1,523, EMAIL 965,
  PERSON_NAME 6,388).
- Pseudonym collisions resolved: FIRST_NAME 1, claim_id 35, customer_id 7.
- **k-anonymity on customers (city, age, gender): k=1 before any fix, a real FAIL** with 182
  rows in classes smaller than 5.
  - Generalization alone (age → 20-year bins, city → region) still gives k=1, because rare
    age/region/gender combinations remain.
  - The best fix, `widen_age+region_city+suppress`, reaches k=5 by suppressing 43 rows.
  - `suppress` alone needs 182 rows.
- Verdict: FAIL without a fix (correct), PASS with `--apply-fix auto`. Exit codes are 2 and 0.
- A masked run takes about 25 s end to end on a laptop CPU. The leak scan over 64k cells is
  about 10 s of that.

Tests: 162 passed. They cover:
- empty leak scan on the demo;
- deliberate leaks causing FAIL: an Arabic-Indic spaced ID in text, an ID glued so only the
  exhaustive pass sees it, structured mobile/ID columns, and a kept full name;
- a human "keep" override on a DIRECT_ID column causing FAIL and withholding the twin;
- schema validation, and the original k FAIL staying visible;
- the CLI end to end, with no identifier, name or key in the logs or the report.

### M6a: Minimal Streamlit flow
- `streamlit run nazeerpp.py`. One page with these steps:
  1. **Load:** a demo button or CSV upload.
  2. **What Nazeer found:** keys/FKs, a column tag table (color by tag, confidence, review
     flag, reason), baseline vs Nazeer counts per identifier type, recall/precision against
     the demo answer key, and a side-by-side note viewer highlighting baseline spans vs
     Nazeer spans.
  3. **Run:** masked or synthetic. Synthetic arrives in M7.
  4. **Evidence:** verdict banner, check table, original vs twin side by side, a zip
     download (twin + report.json, or the report only if the twin is withheld), the full
     JSON and the limitations.
- Errors show a generic message. The details go to the filtered log (type and frames only).
- Verified: `tests/test_app.py` drives the full flow headlessly with Streamlit `AppTest`, and
  checks that a missing key gives a message, not a traceback. A real
  `streamlit run --server.headless true` answered `/_stcore/health` = ok and bound to
  localhost only.
- Tests: 164 passed.

### M7: Synthetic twin 5b + fidelity + TSTR + DCR (done, committed as "WIP: pause")
Command:
`python -m nazeer.pipeline --csv data\demo --mode synthetic --target "is_large_claim=amount>p90" --out out\synthetic`

Results on the full demo (seed 0):
- **holdout_split: PASS.** 20% of customers (600 customers, 2,060 holdout rows) were split
  off before fitting. Train has 5,700 view rows; the twin has 5,700 rows.
- **leak_scan: PASS.** 0 original identifiers in 57,000 twin cells.
- **exact_copies: PASS.** 0.
- **dcr: PASS, with a thin margin.**
  - median DCR twin→train 0.13368 ≥ holdout→train 0.13097;
  - 52% of twin rows are closer to train than to holdout (ideal 50%).
- **utility_tstr: PASS.** Worst AUC drop 0.0023 (limit 0.05):
  - LR 0.9842 → 0.9838;
  - RF 0.9841 → 0.9818.
- **Fidelity (info):** SDMetrics quality 0.9446, mean per-column distance 0.0547, numeric
  correlation diff 0.033.
- Run time is about 22 s warm: analyze 1.4, fit+sample 9.3, TSTR 3.4, leak 5.7. A cold
  start adds imports.

What was built:
- `nazeer/synth.py`: protocol, `SynthSchema`, the SDV single, stratified and HMA adapters,
  `split_holdout`, `build_view`, `view_plan`, `fill_synthetic`.
- `nazeer/text_templates.py`: the synthetic note templates.
- `evaluate.py`: `fidelity`, `sdmetrics_quality`, `parse_target`, `utility_tstr`, `dcr`.
- `pipeline.run_synthetic` and the CLI flags `--target` and `--synthesizer`.
- The UI: target input, synthesizer select, metric panels, and original vs twin.

Tests: 176 passed (`tests/test_synth.py` adds 11, `test_app.py` adds the synthetic UI flow).
They include:
- the split being disjoint by customer;
- the stratified copula picking claim_type, and falling back without a driver;
- fresh, valid identifiers never equal to originals;
- no real note or sentence reused;
- names following the synthetic gender;
- **a memorizing "synthesizer" failing DCR and exact copies**;
- TSTR on a real copy giving no drop.

### R1: DCR robustness check
Command: `python -m nazeer.pipeline --csv data\demo --mode synthetic --target "is_large_claim=amount>p90" --out out\synthetic`
(5 robustness seeds; about 48 s in total)

- **Main run (seed 0): DCR PASS.** Median twin→train 0.13514 ≥ holdout→train 0.13097, and
  53% of twin rows are closer to train than to holdout. Utility worst AUC drop 0.0034;
  SDMetrics quality 0.942.
- **Robustness over 5 splits: the DCR rule holds in only 1/5.**
  - twin→train median 0.1316 ± 0.0029 (sd);
  - holdout→train median 0.1371 ± 0.0069;
  - mean margin −0.0056 (range −0.0189 … +0.0042);
  - closer-to-train share 51% ± 1%.

  **Honest reading:** the seed-0 PASS is partly luck. The stratified twin is consistently
  about 4% closer to the training data than unseen real rows are. It is not copying rows
  (0 exact copies, and the closer-to-train share is near the 50% ideal), but the margin is
  real and slightly negative.
- **Per stratum (main run):** 6/8 claim types pass. أسنان and عمليات جراحية are closer to
  train than holdout.
- **Trade-off measured over the same 5 splits:**

  | synthesizer | DCR rule passed | mean margin | mean AUC drop |
  |---|---|---|---|
  | plain Gaussian copula | 4/5 | +0.0056 | 0.327 (fails utility) |
  | stratified, min 100 rows (default) | 1/5 | −0.0056 | 0.003 |
  | stratified, min 300 rows | 2/5 | −0.0037 | 0.038 |

  Stratifying buys utility at a small DCR cost. The default stays at stratified/100.
  Even the plain copula's margin goes negative on one seed, which shows that the DCR rule
  is noisy at this data size (about 5,700 training rows). This is listed as a top risk.
- Tests: 178 passed. They add a pooled-fallback test (sizes per stratum preserved) and a
  per-stratum DCR + robustness test.

### M6b: UI polish + overrides + k-anonymity Apply
- Under the detection table there is a "Review and override detections" expander
  (`st.data_editor`). It opens automatically when columns need review. Overrides are shown
  live, invalid combinations (DIRECT_ID with no type) are rejected with a message, and every
  override is recorded as `human_reviewed` in the report.
- After a masked run, a k-anonymity panel shows k before, k now, and the rows in small
  classes. When k < k_min it lists the suggested fixes (what each does, k before → after,
  rows affected, whether it reaches k_min), with a "Fix to apply" select and an
  "Apply fix and re-run" button. Nothing is applied automatically. After applying, the panel
  shows the fix, and the report keeps the original FAIL.
- Tests: 185 passed.
  - `test_ui_logic.py` (6): edits → overrides round trip; DIRECT_ID without a type rejected;
    overrides recorded; un-tagging notes → leak FAIL and twin withheld; a newly tagged
    free-text column gets scanned and replaced.
  - `test_app.py` (+1): an override is recorded in the UI run, and the Apply button re-runs
    with the chosen fix (k_before kept, applied_fix recorded).

### MySQL input + output: code and unit tests done, live steps waiting for credentials
- New: `nazeer/mysqlio.py`, `data_gen/load_mysql.py`, `.env.example` (committed), `.env`
  (placeholders, gitignored; verified not staged).
- CLI: `--mysql-db <source>` (instead of `--csv`) and `--mysql-target <target>`. A target equal
  to the source is refused before any work.
- UI: a "Connect to MySQL" box next to CSV upload, plus a "Write twin to database" checkbox and
  target name.
- **Status: waiting for credentials.** `.env` still has `NAZEER_MYSQL_PASSWORD=CHANGE_ME`, and
  the local MySQL service `wampmysqld64` (MySQL 9.1.0, WAMP, `D:\Server\bin\mysql\mysql9.1.0`)
  is **stopped** (manual start). I did not start it.
- **To finish the MySQL part (user):**
  1. Start the service: `Start-Service wampmysqld64` (or start WAMP).
  2. In `.env`, set `NAZEER_MYSQL_PASSWORD` to the root password. For WAMP's default root
     with no password, use `NAZEER_MYSQL_PASSWORD=` with an empty value.
  3. Load the demo: `python -m data_gen.load_mysql` (creates `nazeer_prod_demo`).
  4. Run the tests: `python -m pytest tests\test_mysql.py -rs`. The 4 integration tests should
     run instead of skipping.
  5. Demo: `python -m nazeer.pipeline --mysql-db nazeer_prod_demo --mysql-target nazeer_dev --mode masked --apply-fix auto --out out\mysql_masked`
- **Not yet verified against a live server:** the SQL for reading information_schema,
  creating the target tables with PK/FK, and inserting. The 4 integration tests cover this,
  but they are currently skipped.
- Tests: 210 passed, 4 skipped (reason: waiting for credentials).
  - Unit tests: placeholder → waiting; `.env` read, with real environment variables winning;
    empty password allowed; credentials never in repr; source, system and invalid targets
    refused (also in the CLI before any work, and in `write_twin` before connecting); type
    mapping; value conversion; parent-first table order.
  - UI tests: a missing password shows "waiting for credentials"; writing to the source
    database is refused with a visible message.

### Independent evaluation harness (done; waiting for teammates' notes)
- `python -m nazeer.eval_human --notes data\human_notes.csv` strips the `⟦TYPE:value⟧` markers,
  runs Nazeer and the baseline on the clean text, and prints recall/precision per type, overall,
  and on format-valid identifiers only. It lists every missed span and every extra span by
  **type and position only**, and writes `out\human_eval.json`.
- `data\human_notes_TEMPLATE.csv` (committed): 5 example rows with fake but valid identifiers,
  Arabic-Indic and spaced digits, `+966`, a grouped IBAN, names with and without a family name,
  and two unmarked invoice/order numbers that fail the checksum. Score on the template:
  Nazeer 9/9 (recall 1.0, precision 1.0); baseline recall 0.111, precision 0.333. Five rows
  are a format check, not evidence.
- `docs\HOW_TO_WRITE_NOTES.md`: the Arabic guide for teammates (no real data, how to mark,
  what NOT to mark, how to vary styles, how to run).
- **Real human-notes results: pending.** `data\human_notes.csv` does not exist yet. The file is
  gitignored.
- Tests: 221 passed, 4 skipped (MySQL credentials). `test_eval_human.py` (11) covers marker
  parsing and clean text, malformed markup rejected, the template scored with no values in
  the output, misses and invalid-format reported by position only, an unmarked but
  checksum-valid invoice number surfacing as an honest "extra" (false positive), valid
  `--make-ids`, and a helpful message when the file is missing.

### "Why it works" tab
- The app now has two tabs, "Nazeer" (the flow) and "Why it works". The second shows 5 rows of
  root cause → Nazeer component → live metric from the current session:
  1. **TSTR AUC drop**, after a synthetic run with a target.
  2. **% of fake identifiers passing the official validators** and the **orphan-FK count** in
     the twin.
  3. **Recall, Nazeer vs baseline**: against the answer key for the demo, raw counts otherwise.
  4. **Supported Saudi types**, plus the local-only configuration facts.
  5. **Current verdict and leak count.**

  It also states that detection numbers on generated data do not predict real-data
  performance. It never mentions criteria or weights.
- Tests: 224 passed, 4 skipped (MySQL credentials).

### Arabic NER: CamelBERT + gazetteer fallback
- `nazeer/camel_ner.py` provides `CamelNER` (local-only, batched, with a time budget and model-error
  fallback) and `UnionNER`. `ner.get_name_detector()` selects the mode. Detection batches name
  spans per column (`find_many`).
- Model: `CAMeL-Lab/bert-base-arabic-camelbert-msa-ner` (Apache-2.0), revision
  `54e2905e7c756883b00877cd48ed710a304af0d1`, downloaded once by `scripts\download_models.py`.
- **Names only, first 400 demo notes (385 planted names):**

  | detector | recall | precision | exact spans | name-like words flagged | speed |
  |---|---|---|---|---|---|
  | gazetteer | 0.971 | 1.000 | 374/385 | 0/65 | about 0.5 ms/note |
  | CamelBERT | 0.940 | 1.000 | 253/385 | 0/65 | about 300 ms/note |
  | CamelBERT + gazetteer | **0.990** | 1.000 | 380/385 | 0/65 | about 215 ms/note |

  Cold model load took 84 s the first time (8 s warm).
- **Full demo: 7,160 notes, 6,512 planted names, 1,107 name-like words.**

  | detector | recall | precision | exact spans | name-like words flagged | time |
  |---|---|---|---|---|---|
  | gazetteer | 0.981 | 1.000 | 6,388/6,512 | 0/1,107 | 1 s |
  | CamelBERT | 0.943 | 0.9999 | 4,530/6,512 | 0/1,107 | 863 s (121 ms/note) |
  | CamelBERT + gazetteer | **0.994** | 0.9998 | 6,468/6,512 | 0/1,107 | 888 s (124 ms/note) |

  The speed wording in the README, UI and CLI help was corrected from "~0.2 s" to the measured
  ~0.12 s per note.
- Template notes (5 rows) with the union: Nazeer recall 1.0 and precision 1.0; baseline 0.111 and
  0.333.
- Tests: 232 passed, 4 skipped (MySQL credentials).
  - `test_ner.py` (8): PERS-only spans with a score threshold; model error → gazetteer; time
    budget → gazetteer for the remaining texts; union merge; batched detection; and the
    **real offline model** matching or beating the gazetteer on a fresh demo sample.
  - `test_internal_only.py` now also covers the new README.
- README rewritten in Arabic and English: problem, what it does, users, components,
  PowerShell install/run, MySQL flow, UI steps, metric meanings, known limitations. There is
  no commercial section and no criteria.

### UI redesign for clarity (presentation only)
**Why:** the first audience sees Nazeer for the first time on a projector and must get the story in under
three minutes. The old UI was one long English page with every table, control and metric at once, small
text, and no guidance.

**What changed (`nazeer/app.py`, `nazeer/ui_logic.py`, `nazeer/static/`, `.streamlit/config.toml`):**
- **Guided flow:** a four-step stepper (**١. البيانات ← ٢. الكشف ← ٣. النظير ← ٤. الإثبات**), one primary button
  per step, a "رجوع" (back) button, "إعادة البدء" (start over), and two secondary tabs, **ليش يشتغل؟** and
  **جرّب نصّك**.
- **Demo mode by default:** one button loads the demo data and the preset demo key (deviation 55).
- **Advanced settings:** CSV upload, MySQL, name detector, synthetic mode (labelled "تجريبي" with its
  trade-off), seed, write-to-database and the column-review editor are collapsed under "إعدادات متقدمة".
- **Customer tracking:** one customer is followed through all steps. By default it is the customer whose
  notes best show what a generic tool misses (on the seed-42 demo, مصعب الحمدان · 102009).
- **Step 2 (detection):**
  - two cards: found / false alarms. Generic tool 2,987 / 707; Nazeer 15,865 / 0, out of 15,989 planted.
  - the same note side by side. Every highlight has a color and a text label: هوية، جوال، آيبان، بريد، اسم،
    للمراجعة، رُفض، إنذار كاذب.
- **Step 3 (twin):** a before/after view of the tracked customer and their claims, with changed cells marked.
  Live checks show equal row counts, equal amount totals and 0 broken links.
- **Step 4 (proof):** four cards: leaks, validity of the fakes, link integrity, and k-anonymity.
  - k shows FAIL first, with "طبّق الإصلاح المقترح" (the recommended fix): **k = 1 → 5**, then PASS.
  - "ازرع تسريباً" writes the tracked customer's real ID (Arabic digits, spaced) into a **copy** of the twin
    and runs the pipeline's own leak scan, which turns FAIL. The delivered twin is untouched (tested).
- **Visual design:**
  - Arabic RTL throughout, with numbers LTR-isolated (deviation 60).
  - 18 px base font and large headline numbers.
  - One palette, defined in `nazeer/static/nazeer.css` and the `[theme.light]` / `[theme.dark]` sections of
    `config.toml`: original = blue, twin = violet, detected = red, needs review = amber.
  - Plain-Arabic tooltips on k, recall, false alarm, checksum, DCR, AUC and TSTR.
  - Friendly Arabic error messages.
- **No network:**
  - IBM Plex Sans Arabic (SIL OFL 1.1, license file next to the font) is served from `nazeer/static/fonts/`
    by Streamlit static serving.
  - Verified with Playwright that the browser makes no request outside localhost.
  - The emoji favicon is an inline SVG. Material icons are avoided, because a material favicon would load
    from gstatic.

**Unchanged:** `pipeline.py`, `detect.py`, `transform.py`, `evaluate.py`, `kanon.py`, `report.py`, policy and
thresholds, and every metric. All numbers on screen come from those modules.

**Tests: 241 passed, 4 skipped** (MySQL credentials):
- `test_app.py` adds `test_demo_walkthrough_four_steps`, an AppTest smoke run of the pitch path with no key
  typed: load → detect → generate → proof → apply fix (PASS) → plant leak (caught, twin untouched) → reset.
  It also adds `test_try_your_text_tab`.
- `test_ui_logic.py` adds 7 tests: tracking, labels for rejected look-alikes and baseline false alarms, the
  no-answer-key summary, totals, proof cards, the planted leak, the text-masking preview, and the "why" rows.

**Screenshots:** `docs\ui\before-*.png` and `docs\ui\after-*.png` (light and dark), indexed in
`docs\ui\README.md`. Regenerate them with `scripts\ui_screenshots.py`. Playwright is a documentation tool
only, not a project dependency.

**Demo script:** the click paths in `docs\internal\DEMO_SCRIPT.md` now follow the new UI.

## Final status (2026-10-01)

All numbers are from the final runs in `out\` (summary: `out\METRICS_SUMMARY.md`, built by
`python scripts\summarize_runs.py`). Tests: **241 passed, 4 skipped** (after the UI redesign; 232 before). The 4 skipped are the live
MySQL integration tests, waiting for credentials.

### Complete
- M0–M5, M6a, M6b, M7 (as planned, plus deviations 1–54 above).
- R1 DCR robustness: 5 seeds, per-stratum DCR, and a pooled fallback for strata under 100 rows.
- MySQL input/output: code, CLI, UI and unit tests (read-only source, separate utf8mb4 target,
  same PKs/FKs, refuses the source, leak scan re-run on the target).
- Independent evaluation harness: `python -m nazeer.eval_human`, a template, and the Arabic
  writing guide.
- "Why it works" tab with five live metrics, and a guard test that keeps criteria and weights
  out of every judge-facing file.
- Arabic NER: CamelBERT + gazetteer union (optional), and the gazetteer default.
- UI redesign: a four-step Arabic flow, demo mode with no typing, customer tracking, proof cards with the
  k-anonymity fix and a planted-leak demo, and no network requests (see "UI redesign for clarity").
- Final deliverables:
  - bilingual README (no commercial section, no criteria);
  - demo runs `out\masked_no_fix`, `out\masked`, `out\synthetic`, `out\detection_scores.json`
    and `out\METRICS_SUMMARY.md`;
  - `docs\internal\DEMO_SCRIPT.md`.

### Final demo numbers (seed 42, 3,000 customers, 7,160 claims)

| | result |
|---|---|
| Free-text detection (15,989 planted) | Nazeer recall **0.992**, precision **1.000**; baseline 0.187 / 0.809 |
| Look-alikes wrongly flagged | Nazeer **0** / 6,756; baseline 707 / 6,756 |
| Masked twin | verdict **PASS** with fix (FAIL without); leak scan 0 in 63,960 cells; exact copies 0; 15,865 spans replaced; fake IDs/mobiles 100% valid; 0 orphan FKs |
| k-anonymity | **k=1 → 5** with `widen_age+region_city+suppress` (43 of 3,000 rows suppressed; 233 → 67 classes) |
| Synthetic twin | verdict **PASS**; AUC 0.9842→0.9831 (LR), 0.9841→0.9807 (RF), worst drop **0.0034**; SDMetrics 0.942; exact copies 0; leak scan 0 in 57,000 cells |
| DCR | main run PASS (0.1351 ≥ 0.1310); **robustness 1/5 splits**, mean margin −0.0056 |
| Names (full demo) | gazetteer 0.981; CamelBERT + gazetteer **0.994**; CamelBERT alone 0.943 |
| Hand-written notes | **not available yet** (no `data\human_notes.csv`) |

### Partial
- **MySQL live path: waiting for credentials.** The service `wampmysqld64` (MySQL 9.1.0) is
  stopped, and `.env` still has `CHANGE_ME`. The code is unit-tested, but the 4 live tests
  (Arabic round trip, FK detection, read-only source, prod → dev with a target leak scan) have
  never run. Steps: see the MySQL section above. There is no `out\mysql_masked` run yet.
- **Human-notes evaluation:** the harness is ready, and the teammates' notes are pending.
- **Demo script weights:** the six criteria are in place, but their weights were never provided
  (the message was truncated). The time split is an explicit equal placeholder.

### Not built
- HMA multi-table synthesis and the PDF report: **out of scope for the hackathon** (user decision).
  The `SdvMultiTable` adapter remains as an unused seam.
- Our own scipy copula replacing SDV (only the `Synthesizer` seam exists).
- UI editing of `generalize` parameters (policy file only).

### Top 3 risks before presenting
1. **The "production DB → development DB" demo depends on MySQL, which has never run live here.**
   Start the service, set the password, run `python -m data_gen.load_mysql` and
   `python -m pytest tests\test_mysql.py -rs` **before** the day. If anything fails, use the CSV
   fallback in the demo script (same numbers).
2. **Synthetic privacy margin.** DCR passes on the main run but in only 1/5 holdout splits (the
   twin is about 4% closer to training data than unseen rows). Say it before being asked, along
   with the measured trade-off (the plain copula passes 4/5 but loses all utility).
3. **Detection evidence comes only from generated data**, and demo names come from the gazetteer's
   own lists. Get the teammates' hand-written notes scored with `python -m nazeer.eval_human`
   before the pitch, and put those numbers in the demo script.

## Earlier pause note (historical, superseded by Final status)
- **Current milestone:** M7 is finished. The code is written, the full suite passes
  (176 passed), and real numbers are recorded above. It was committed with the message
  "WIP: pause" instead of "M7: …" because the user asked to stop.
- **Done:** M0, M1, M2, M3, M4, M5, M6a, M7.
- **Half-done:** nothing. No file is mid-edit.
- **Not started:**
  - M6b: UI polish, overrides UX, k-anon Apply button with before/after k.
  - M8: CamelBERT NER with gazetteer fallback, HMA multi-table, PDF report, PostgreSQL input.
  - Final deliverables: bilingual README, demo runs in `out\`, `docs\DEMO_SCRIPT.md`, and the
    final PROGRESS section.
- **Next step when resuming:** M6b.
  1. Add an overrides editor on the detection table: change tag/kind/action per column,
     recorded as `human_reviewed` in the report.
  2. After a masked run with k < k_min, list `report["k_anonymity"][t]["suggestions"]` with
     before/after k and rows affected, and add an "Apply" button that re-runs
     `pipeline.run_masked(..., apply_fix=<name>)`.
  3. Extend `tests/test_app.py` for both, then commit as "M6b: …".
- **How to resume:**
  `cd $HOME\Desktop\nazeer; .\.venv\Scripts\Activate.ps1; python -m pytest`
  (expect 176 passed). Demo data: `python -m data_gen.make_demo_data --seed 42 --n 3000`
  (`data\` and `out\` are gitignored).
- Earlier note: the M5 log originally said "168 passed". That was a typo; the real number was
  162 and has been corrected.

## Known issues

(none yet)

## Next step

Remaining actions are the user's: MySQL credentials + service, hand-written notes, criteria weights (see Final status).
