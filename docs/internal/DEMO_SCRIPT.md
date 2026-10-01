Internal team document — do not share.

# Nazeer: 5-minute demo script (internal)

Structured by the six judging criteria. Every number below comes from the runs in `out\`
(regenerate them with the commands at the end and check `out\METRICS_SUMMARY.md` before presenting).
The app, README and reports never mention criteria or weights; keep it that way on screen and in speech.

## Time allocation

> ⚠️ **The criteria weights were not provided to the build session.** Replace the placeholder
> weights below with the real ones; the seconds column is `weight × 300 s`.

| # | Criterion | Weight (fill in) | Seconds (placeholder: equal split) |
|---|---|---|---|
| 1 | Problem understanding (causes, who is affected) | ? % | 50 |
| 2 | Solution fit (logical link problem → solution) | ? % | 50 |
| 3 | Innovation vs existing solutions | ? % | 50 |
| 4 | Feasibility (tech and data available) | ? % | 50 |
| 5 | Measurable impact | ? % | 50 |
| 6 | Clarity (how it works, components, who uses it) | ? % | 50 |
| | **Total** | 100 % | **300** |

## Before the pitch (checklist)

1. `Start-Service wampmysqld64` (or start WAMP) and put the real password in `.env`
   (`NAZEER_MYSQL_PASSWORD=`; empty if WAMP root has none). **MySQL is still "waiting for credentials".**
2. `python -m data_gen.load_mysql --replace` → creates `nazeer_prod_demo` (3,000 customers, 7,160 claims).
3. `$env:NAZEER_KEY = "<32+ random characters>"`, then `streamlit run nazeer\app.py`.
4. Warm-up click-through once (first analysis takes ~2 s, a masked run ~25 s, synthetic ~50 s with
   the 5-seed DCR robustness). Keep "Name detection: Fast" selected (CamelBERT is ~0.12 s/note on CPU: ~15 min for all demo notes).
5. Have `out\METRICS_SUMMARY.md` open in a second window as a backup if anything is slow.
6. **Fallback if MySQL is not ready:** click "Use demo dataset" instead of "Connect to MySQL"; the
   numbers are identical (same seeded data), only the "production DB → development DB" framing changes.

## Demo flow: production database → Nazeer → development database

### 1 · Problem understanding — 50 s (placeholder)
**Say:** "Every Saudi bank, hospital and government entity has the same dilemma. Developers, testers and
data scientists need realistic data. Copying production breaks the PDPL. Random fake data breaks
validation — a fake national ID fails the checksum, a fake IBAN fails mod-97 — and destroys joins.
And the worst leak is the one nobody sees: identifiers typed into Arabic notes, in Arabic digits,
with spaces, as +966."
**Who is affected:** data owners, data-protection officers who must approve copies, dev/test/AI teams.
**Click:** none yet — or show one raw note from the demo in the app (step 2 note viewer, left side).

### 2 · Solution fit — 50 s (placeholder)
**Say:** "Nazeer runs inside production, operated by the data owner — nothing leaves the machine.
It produces a twin with no real people and an evidence report that the officer can sign off."
**Click:** "Nazeer" tab → "Connect to MySQL" with `nazeer_prod_demo` (read-only) → step 2 appears.
Then open the **"Why it works"** tab and read the five rows: each root cause → the component → the
live metric. (Come back to it in part 5 after the run.)

### 3 · Innovation vs existing solutions — 50 s (placeholder)
**Say:** "Generic tools use ASCII regexes. On our Arabic notes a generic regex finds **18.7%** of
identifiers and **flags 707 invoice numbers** as IDs. Nazeer normalizes Arabic-Indic and Persian
digits, joins digits split by spaces or hyphens, and keeps a character map back to the original —
then **every candidate must pass the official checksum**. Result: **99.2% recall, 100% precision,
0 of 6,756 look-alikes flagged**."
**Click:** step 2 → the comparison table and the note viewer (pick the first note in the list:
left = baseline marks, right = Nazeer marks).
**Also say:** pseudonyms are keyed HMAC — same person → same fake across tables, columns and free
text, with **no mapping table stored**, and the fake keeps the original's digit script and spacing.

### 4 · Feasibility — 50 s (placeholder)
**Say:** "Everything here runs today on a laptop: Python, a local MySQL, a local Streamlit app, an
Arabic NER model loaded from local disk. Input is a CSV folder or a MySQL database read with
SELECT-only, read-only sessions; output goes to a **separate** development database — Nazeer refuses
to write into the source."
**Click:** step 3 → tick "Write twin to database", target `nazeer_dev` → **Run Nazeer** (masked).
While it runs (~25 s), mention: 232 automated tests (+4 live-MySQL tests); the run would refuse a target equal to the source.

### 5 · Measurable impact — 50 s (placeholder)
**Say (masked twin, `out\masked`):**
- **15,865** identifiers replaced inside free text; **100%** of fake IDs and mobiles pass the official
  validators; **0** orphan foreign keys across 7,160 claims — joins still work.
- Leak scan: **0** original identifiers in **63,960** twin cells (detector + independent exhaustive search),
  re-checked after reading the twin back from the development database.
- **0** exact copies.
- k-anonymity: honest **FAIL at k = 1** first → click the suggested fix → **k = 5** by generalizing age
  and city and suppressing **43 of 3,000** rows. The report keeps the original FAIL visible.
**Click:** step 4 → verdict, checks table → k-anonymity panel → "Apply fix and re-run" → verdict PASS.
**Then (synthetic twin, `out\synthetic`) — say, or switch mode and run (~50 s):**
- A model trained on the twin predicts large claims on **real held-out data** almost as well as one
  trained on real data: AUC **0.984 → 0.983** (logistic regression), **0.984 → 0.981** (random
  forest); worst drop **0.0034** (limit 0.05). SDMetrics quality **94.2%**. 0 exact copies.
**Click:** "Why it works" tab — all five live metrics now filled in.

### 6 · Clarity — 50 s (placeholder)
**Say:** "Four steps — load, detect, generate, prove — and three users: the data team runs it, the
data-protection officer reads the PASS/FAIL report, developers get the twin in `nazeer_dev`."
**Click:** step 4 → "Download twin + report" and expand "Full report (JSON)" → "Known limitations".
**Close with:** "Nazeer turns 'please trust us' into a report with numbers — and it tells you when
it fails."

## Caveats to say if asked (be upfront, never hide)

- **Detection numbers on generated data do not predict real-data performance.** They show the planted
  formats are covered. The demo names come from the same lists as the name gazetteer, so name recall
  (98.1%) on the demo is optimistic.
- **Hand-written notes (independent test): not available yet.** Teammates have the guide
  (`docs\HOW_TO_WRITE_NOTES.md`); run `python -m nazeer.eval_human` and add the numbers here when ready.
  (The 5-row template scores 9/9 for Nazeer vs 1/9 for the baseline — a format check, not evidence.)
- **DCR robustness:** the synthetic twin passes the DCR rule on the main run, but in only **1 of 5**
  different holdout splits; on average the twin is ~4% closer to the training data than unseen rows
  (no exact copies; closer-to-train share 51% ± 1%, ideal 50%). The plain copula passes 4/5 but loses
  all utility (AUC drop 0.33). This is a measured privacy–utility trade-off we show, not hide.
- **The masked twin is still personal data** (each row maps to a real person; the key holder can
  re-identify) — it is for testing inside controlled environments. The synthetic twin is stronger,
  not proven anonymous.
- **MySQL live path** is implemented and unit-tested, but the 4 live integration tests only run once
  the local server is started with real credentials — run `python -m pytest tests\test_mysql.py -rs`
  after the checklist.
- Arabic NER: CamelBERT + name lists raises name recall on the full demo from **0.981 to 0.994**
  (6,512 names; 0 of 1,107 name-like words flagged), but takes ~15 min on CPU for 7,160 notes, so the
  fast name lists are the default. CamelBERT alone: 0.943 — it is independent of our name lists,
  which matters for real text.

## Regenerate the numbers

```powershell
$env:NAZEER_KEY = "<32+ random characters>"
python -m data_gen.make_demo_data --seed 42 --n 3000
python scripts\score_detection.py --json out\detection_scores.json
python -m nazeer.pipeline --csv data\demo --mode masked --out out\masked_no_fix
python -m nazeer.pipeline --csv data\demo --mode masked --apply-fix auto --out out\masked
python -m nazeer.pipeline --csv data\demo --mode synthetic --target "is_large_claim=amount>p90" --out out\synthetic
python -m nazeer.pipeline --mysql-db nazeer_prod_demo --mysql-target nazeer_dev --mode masked --apply-fix auto --out out\mysql_masked
python scripts\summarize_runs.py
```
