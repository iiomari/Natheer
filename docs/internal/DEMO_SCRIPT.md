Internal team document — do not share.

# Nazeer: 5-minute demo script (internal)

This script follows the six judging criteria. Every number below comes from the runs in `out\`.
Regenerate them with the commands at the end and check `out\METRICS_SUMMARY.md` before presenting.

Rules on screen and in speech:
- The app, README and reports never mention criteria or weights. Keep it that way.
- **Lead with the masked twin.** All of its checks PASS honestly.
- Present the synthetic twin **only as an experimental mode**, and state its trade-off. **Never say
  its privacy "passes" in general.**

## Time allocation (5:00)

| # | Criterion | Weight | Time | Clock |
|---|---|---|---|---|
| 1 | Problem understanding (causes, who is affected) | 20 % | 60 s | 0:00–1:00 |
| 2 | Solution fit (logical link problem → solution) | 20 % | 60 s | 1:00–2:00 |
| 3 | Innovation vs existing solutions | 15 % | 45 s | 2:00–2:45 |
| 4 | Feasibility (tech and data available) | 20 % | 60 s | 2:45–3:45 |
| 5 | Measurable impact | 15 % | 45 s | 3:45–4:30 |
| 6 | Clarity (how it works, components, who uses it) | 10 % | 30 s | 4:30–5:00 |

## Before the pitch (checklist)

1. Start MySQL: `Start-Service wampmysqld64` (or start WAMP). Put the real password in `.env`
   (`NAZEER_MYSQL_PASSWORD=`, left empty if WAMP's root account has none).
2. Run `python -m data_gen.load_mysql --replace`. This creates `nazeer_prod_demo` with 3,000
   customers and 7,160 claims. Then run `python -m pytest tests\test_mysql.py -rs`: the 4 live tests
   must pass, not skip.
3. Set `$env:NAZEER_KEY = "<32+ random characters>"`, then run `streamlit run nazeer\app.py`.
   **The key is required for the MySQL flow.** The demo-data button works without it (it uses a preset
   demo key, only for the generated demo dataset).
4. Click through once to warm up. A masked run takes about 25 s, the k-anonymity fix another ~25 s, and
   "plant a leak" about 3 s. Leave "إعدادات متقدمة → كشف الأسماء" on "سريع" (CamelBERT takes about 15 min
   on CPU for all demo notes).
5. Projector: browser zoom 100%, window at least 1366 px wide. Light and dark both work. Press
   **"إعادة البدء"** (top-left) before you start so the stepper is back at step ١.
6. Keep `out\METRICS_SUMMARY.md` open in a second window as a backup.
7. **Fallback if MySQL is not ready:** click **"تحميل بيانات العرض"** instead of connecting to MySQL. The
   numbers are identical (same seeded data); only the "production DB → development DB" framing changes.

### UI map (new layout, 2026-10-01)
- Top: stepper **١. البيانات ← ٢. الكشف ← ٣. النظير ← ٤. الإثبات**. One purple primary button per step.
- Tabs: **نَظير** (the flow), **ليش يشتغل؟** (5 root-cause rows), **جرّب نصّك** (type any note live).
- Everything else (CSV upload, MySQL, name detector, synthetic mode, write to DB, column review) is in the
  collapsed **"إعدادات متقدمة"** at the bottom of the نَظير tab.
- The tracked customer is chosen automatically (on the seed-42 demo: **مصعب الحمدان · 102009**, whose first
  note has an invoice number, a spaced ID and a +966 mobile in Arabic digits). It stays selected in all steps.
- Screenshots of every step: `docs\ui\after-*.png`.

## Main flow: production database → Nazeer → development database (masked twin)

### 1 · Problem understanding (60 s, 0:00–1:00)
**Say:** "Every Saudi bank, hospital and government entity faces the same dilemma.
- Developers, testers and data scientists need realistic data.
- Copying production data breaks the PDPL.
- Random fake data breaks validation: a fake national ID fails the checksum, a fake IBAN fails
  mod-97, and joins between tables fall apart.
- The worst leak is the one nobody sees: identifiers typed into Arabic notes, in Arabic digits,
  with spaces, written as +966."

**Causes:** production is the only realistic data, generic masking tools don't know Saudi formats,
and free text is never checked.

**Who is affected:**
- the people in the data;
- the data owner;
- the data-protection officer who must approve every copy;
- the development, testing and AI teams who are blocked or work with useless data.

**Click:** "إعدادات متقدمة" → "قاعدة MySQL المصدر" = `nazeer_prod_demo` → **"اتصل بـ MySQL"** (read-only).
Step ١ shows both tables with the tracked customer's rows highlighted ("المتتبَّع"). Point at the notes
column: "it looks normal, but the IDs and mobiles are in there." Then **"التالي: ماذا وجد نظير؟"** and point
at the right-hand box ("أداة تقليدية"): the Arabic-digit mobile and ID are not marked.

### 2 · Solution fit (60 s, 1:00–2:00)
**Say:** "Each cause has a matching component:
- Nazeer runs **inside** production, operated by the data owner, and nothing leaves the machine.
- It finds identifiers in columns and inside Arabic text.
- It replaces them with fakes that are valid and consistent.
- It hands the officer a PASS/FAIL evidence report."

**Click:** the **"ليش يشتغل؟"** tab. Read the five rows: root cause → component → live metric. Then go
back to the **"نَظير"** tab (you are still on step ٢).

### 3 · Innovation vs existing solutions (45 s, 2:00–2:45)
**Say:** "Generic tools use ASCII regular expressions. On our Arabic notes, a generic regex finds
**18.7%** of identifiers and wrongly flags **707 invoice numbers** as IDs.

Nazeer normalizes Arabic and Persian digits and joins numbers split by spaces, while keeping a map
back to the original characters. Then every candidate must pass the **official checksum**.

The result: **99.2% recall, 100% precision, and 0 of 6,756 look-alikes flagged.** Each person gets
the same fake everywhere, through a keyed HMAC with **no stored mapping table**, and the fake keeps
the original's digit script and spacing."

**Click:** step ٢: the two big numbers (**2,987** vs **15,865** of 15,989 found; **707** vs **0** false
alarms), then the note below them. Right box ("أداة تقليدية"): the invoice number is marked **"إنذار كاذب"**.
Left box ("نَظير"): the same number is struck through and labelled **"رُفض"** (fails the checksum), and the
spaced ID and +966 mobile are labelled **"هوية"** / **"جوال"**. Hover any dotted word for a one-line
explanation.

### 4 · Feasibility (60 s, 2:45–3:45)
**Say:** "Everything here runs today on a laptop:
- Python, a local MySQL, and a local app;
- an Arabic NER model loaded from local disk.

Nazeer reads the source with read-only, SELECT-only sessions. It writes the twin to a **separate**
development database with the same keys, and it refuses to write into the source. There are 232
automated tests behind it."

**Click:** **"التالي: ولّد النظير"**. Then, **before generating**, open "إعدادات متقدمة" → tick
**"اكتب النظير في قاعدة بيانات"**, target `nazeer_dev` (masked is the default type). Click **"ولّد النظير"**.
While it runs (about 25 s), mention: "if I typed the production database name here, Nazeer would refuse."
When it finishes, show the before/after of the same customer (changed cells marked ●) and read the line
under it: **"نفس الأعداد والمجاميع والروابط — بدون عميل حقيقي."**

### 5 · Measurable impact (45 s, 3:45–4:30)
**Say (masked twin, every check PASS):**
- "**15,865** identifiers replaced inside Arabic free text."
- "**100%** of fake IDs and mobiles pass the official validators, and there are **0** broken joins
  across 7,160 claims."
- "The leak scan found **0** original identifiers in **63,960** cells. It checked again after
  reading the twin back from the development database."
- "**0** exact copies."
- "k-anonymity: Nazeer first reports an honest **FAIL at k = 1**. I apply its suggested fix: wider age
  bands, city → region, and **43 of 3,000** rows suppressed. Now **k = 5**, and the original FAIL stays
  in the report."

**Click:** **"التالي: الإثبات"**. The banner says **FAIL** and names only "خطر التعرّف بالتركيب"; the four
cards show تسريب **0**, صلاحية البدائل **100%**, سلامة الروابط **0**, and **k = 1 FAIL**. Click
**"طبّق الإصلاح المقترح"** (about 25 s): the card shows **k = 1 → 5** and the banner turns **PASS**.
Then click **"ازرع تسريباً"** under the leak card: a real ID, written in Arabic digits with spaces, goes into
a copy of the twin; the leak card turns **FAIL (1)** and the banner says the twin would be withheld. Click
**"أزل التسريب المزروع"** to return to PASS.

### 6 · Clarity (30 s, 4:30–5:00)
**Say:** "Four steps: load, detect, generate, prove. Three users: the data team runs it, the
data-protection officer reads the PASS/FAIL report, and developers get the twin in `nazeer_dev`.
Nazeer turns 'please trust us' into a report with numbers, and it tells you when something fails."

**Click:** point at the stepper (four steps), then **"تنزيل النظير والتقرير (zip)"**, then expand
**"حدود معروفة"**. If someone wants to try it: the **"جرّب نصّك"** tab takes any typed note.

## Synthetic twin: experimental mode (only if time allows, or if asked)

Say it in exactly these terms. **Do not present its privacy as PASS.**

**Click (only if asked):** "إعدادات متقدمة" → "نوع النظير" → **"اصطناعي (تجريبي)"** (the target is pre-filled
as `is_large_claim=amount>p90`) → step ٣ → **"ولّد النظير"** (about a minute) → **"التالي: الإثبات"**. The
UI labels it experimental and states the trade-off under the cards.

> "We also have an experimental synthetic mode for analytics. It generates brand-new rows. A model
> trained on it predicts large claims on real held-out data almost exactly as well as one trained on
> real data: AUC **0.984 → 0.981**, a worst drop of **0.0034**. But our own privacy check (DCR) shows the
> trade-off.
> - The stratified copula passes the distance test on only **1 of 5** data splits: its rows sit
>   slightly closer to the training data than unseen real rows do.
> - The plain pooled copula passes **4 of 5**, but loses almost all utility (AUC drop **0.33**).
>
> So we don't treat synthetic mode as safe yet."

Facts behind it (`out\synthetic`, 5-split robustness):
- The stratified model's main run passes DCR (0.1351 vs 0.1310), but the rule holds in 1/5 splits.
- Mean margin −0.0056, about 4% closer to train.
- Closer-to-train share 51% ± 1% (ideal 50%).
- 0 exact copies, and the leak scan found 0 identifiers in 57,000 cells.
- **Time-boxed improvement attempt:** see "Synthetic privacy experiment" in `docs\PROGRESS.md`.
  The outcome is recorded there; this script is updated if a variant was adopted.

## Ready answers

- **"Is the synthetic data safe?"** → "Our own tool flagged that the synthetic mode still sits too close
  to the original data, so we don't treat it as safe yet. The masked twin is what we deliver today,
  and every one of its checks passes."
- **"Isn't the masked twin still personal data?"** → "Yes, most likely. Each row maps to a real person
  and the key holder could re-identify. It is meant for testing inside controlled environments, and the
  report says so."
- **"How good is detection on real text?"** → "Our 99.2% is on generated notes, so it shows our
  planted formats are covered. It doesn't predict real text. That's why teammates wrote notes by hand
  without seeing the generator: [hand-written notes results here, or: 'that evaluation is in
  progress']." The demo names also come from the same lists as our name gazetteer, so name recall on
  the demo is optimistic. CamelBERT alone, which is independent of those lists, reaches 0.943, and
  CamelBERT + lists reach 0.994.
- **"What if a fake ID belongs to a real person?"** → "A fake never equals any original in the dataset,
  but a valid-looking fake can coincide with someone outside it. That's stated in the report."
- **"Could you write into production by mistake?"** → "No. The source is opened read-only, and a target
  equal to the source is refused before any work starts. That's tested."

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
