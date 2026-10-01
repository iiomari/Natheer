# Nazeer (نَظير): Implementation Plan

## Context
Saudi organizations need realistic non-production data. Production copies violate data-protection rules, and random fake data breaks validation, relationships and analytics. Nazeer runs inside production, operated by the data owner. It turns relational tables into a **masked twin** (5a) or a **synthetic twin** (5b) and produces an evidence report of measured privacy and utility. What sets it apart is Saudi-aware detection: checksummed IDs, mobiles and IBANs, including Arabic-Indic digits and spaced digits hidden in Arabic free text.

Environment facts verified during planning (not from memory):
- The machine has Python 3.11.9. The global site has **pandas 3.0.0 and torch 2.2.2**. SDV/SDMetrics require `pandas<3` and transformers 5.x requires `torch>=2.5`, so an isolated venv is **mandatory**, not optional.
- The spec's test vectors check out. Valid IDs `1110704341`, `1909266858` and `2129040479` pass. Invalid IDs `1234567890` and `2111111111` fail. `SA0380000000608010167519` gives mod-97 = 1 and is 24 characters long.
- The repo location is a new folder `C:\Users\iomar\Desktop\nazeer\` with its own `git init`. The current `Desktop\python` folder is an unrelated mixed workspace.

---

## 1. Summary of understanding (5 lines)
1. Nazeer is a local Python tool (CLI + Streamlit) that reads a CSV folder or PostgreSQL. It profiles schema and keys, then detects personal data at column level and inside Arabic free text.
2. Detection is Saudi-aware: digits are normalized (Arabic-Indic/Persian, spaced), with an offset map back to the original text. A checksum/mod-97 validator gate removes look-alike numbers. Names come from Arabic NER, with a gazetteer as fallback.
3. The masked twin applies keyed HMAC pseudonymization. It is consistent across tables, columns, free text and runs, and it preserves format (digit script, spacing, prefix style) and FK joins. Generalization comes from a YAML policy plus human overrides.
4. The synthetic twin uses SDV trained on an 80% split, never the 20% holdout. It excludes direct IDs, then fills IDs with our generators and free text from templates. No real text is ever reused.
5. Every run ends with an evaluation and an honest JSON report with a PASS/FAIL verdict. The evaluation covers fidelity, TSTR utility, exact copies, DCR, k-anonymity and a hard-fail leak scan.

---

## 2. Milestones (priority order; cut from the bottom)
Effort is in engineer-hours. The cumulative column shows where the cut line falls: **the cut line is the last row whose cumulative hours ≤ (team size × usable hours before the deadline)**. The deadline and team size are still unknown (see open questions), so the line can't be marked yet. M0–M2 are sequential. After M2, M3/M4 and M5/M7 can run in parallel.

| # | Milestone | Files | Done means (testable) | Effort | Cum. |
|---|---|---|---|---|---|
| M0 | Setup + dependency verification | `requirements.txt`, `requirements-lock.txt`, `pyproject.toml`, `.gitignore`, `.streamlit/config.toml`, `scripts/download_models.py`, `scripts/smoke_api.py`, `docs/api_notes.md`, `nazeer/safe_log.py`, `nazeer/config.py` | The `.venv` on 3.11 installs cleanly and `pip freeze` goes to the lock file. The smoke script prints the real signatures of the SDV `Metadata`/`GaussianCopulaSynthesizer`/`HMASynthesizer`/`evaluate_quality`, noted in `api_notes.md`. `load_key()` fails fast without `NAZEER_KEY`. `git init` is done locally. | 3 | 3 |
| M1 | `saudi_ids` + normalization | `nazeer/saudi_ids.py`, `nazeer/data/names_*.csv`, `tests/test_saudi_ids.py` | All vectors pass. 1,000 outputs per generator pass their validator. Offset-map property tests pass. | 5 | 8 |
| M2 | Demo data + golden labels | `data_gen/make_demo_data.py`, `data_gen/templates_ar.py`, `data/demo/*.csv`, `data/demo/golden_labels.csv` | Output is byte-identical across two seeded runs. Every golden span validates. Hard negatives fail validation. | 6 | 14 |
| M3 | Profile + detection + baseline | `nazeer/profiling.py`, `nazeer/detect.py`, `nazeer/ner.py`, `nazeer/types.py`, `tests/test_detect.py` | The demo FK is found. Tags are correct. Identifier recall ≥ 0.90 on golden labels. Baseline vs Nazeer numbers are printed. | 8 | 22 |
| M4 | Policy + transform | `config/policy.yaml`, `nazeer/policy.py`, `nazeer/transform.py`, `tests/test_transform.py` | Determinism holds ×100 and across 2 processes. Joins are preserved. Format is preserved. No fake equals an original. | 8 | 30 |
| M5 | Evaluation core + report + k-anon suggestions (backend) | `nazeer/evaluate.py`, `nazeer/kanon.py`, `nazeer/report.py`, `nazeer/pipeline.py` (CLI), `tests/test_leak.py`, `tests/test_kanon.py` | A masked CLI run on demo gives an empty leak scan, 0 exact copies and a k figure. Deliberate leak → FAIL. When k < k_min, `suggest_fixes()` returns candidates with before/after k, and the report records both the original FAIL and the applied fix. | 8 | 38 |
| **M6a** | Minimal Streamlit flow | `nazeer/app.py` | Upload CSV folder → detection + baseline panel → run → metrics → download twin + report, all working on demo. | 5 | 43 |
| **M7** | Synthetic 5b single-table (GaussianCopula) + fidelity + TSTR + DCR | `nazeer/synth.py` (`Synthesizer` protocol + SDV adapter), `nazeer/text_templates.py`, extend `evaluate.py`, `tests/test_synth.py` | The split happens before fit (asserted). The twin is produced through the protocol. KS/TVD/corr-diff are reported. The AUC drop for LR + RF is reported against `max_utility_drop` (absolute). DCR medians and the "closer to train" share are reported. | 8 | 51 |
| **M6b** | UI polish + overrides UX + k-anon apply UI | `nazeer/app.py` | Overrides are recorded in the report. The k-anon suggestions show before/after k with an Apply button. | 4 | 55 |
| M8 | Stretch: HMA multi-table, CamelBERT NER, PDF, **PostgreSQL input** | `synth.py` (HMA adapter), `ner.py`, `report.py`, `nazeer/io.py` | HMA keeps FK integrity. NER vs gazetteer recall is measured. PDF works. Postgres read-only load works with FKs from `information_schema`. | 11 | 66 |

**Never cut:** Arabic free-text detection (M3), the leak scan (M5), honest reporting (M5), **TSTR and DCR (M7)**.

### Proposed changes to the repo structure
- **`profile.py` → `profiling.py`**, because `profile` is a stdlib module and shadowing it causes confusing import bugs when running scripts from inside the package.
- **Add `types.py`** for shared dataclasses (`Span`, `ColumnProfile`, `ColumnDetection`, `Decision`, `RunResult`), to avoid circular imports.
- **Add `io.py`** with `load_csv_folder` and `write_csv_folder` in the MVP (pathlib only). `load_postgres` comes in M8. The twin is always written as a CSV folder and never back to any DB.
- **Add `kanon.py`** with `k_anonymity(df, quasi_cols) -> KResult` and `suggest_fixes(df, quasi_cols, k_min, rules) -> list[Fix]`. Fix types are widening age bins (10 → 20 years), mapping city → region (a hand-written Saudi city→region table), and suppressing small classes. Each `Fix` carries `k_before`, `k_after` and `rows_affected`, and the pipeline takes `applied_fixes` as input.
- **Add `ner.py`** for the `NameDetector` protocol with `CamelNER` and `GazetteerNER`, so detect.py stays testable without torch.
- **Add `safe_log.py`**: a logging filter plus an exception wrapper that strip values (see risks).
- **Add `text_templates.py`**: the 5b template library, kept separate from the demo generator's templates so that synthetic text is never the demo text.
- **Add `scripts/download_models.py`** for the only network step. The runtime sets `HF_HUB_OFFLINE=1`.

---

## 3. Libraries and versions
These are target pins. M0 installs them and freezes the fully resolved set into `requirements-lock.txt`. Versions marked † were checked on PyPI during planning. The rest are to confirm at M0.

| Library | Pin | Why |
|---|---|---|
| python | 3.11.x | Constraint. SDV supports 3.9–3.14. |
| pandas | `>=2.2,<3` (freeze exact) | SDV/SDMetrics require `<3` †. |
| numpy | resolved by pandas/SDV | — |
| sdv | `==1.38.5` † | GaussianCopula, CTGAN and HMA synthesizers, plus the Metadata API (`detect_from_dataframes`, `add_relationship`, `update_column`, `validate_data`) †. **BUSL-1.1** †. |
| sdmetrics | `==0.32.0` † | Quality report. **MIT** †. |
| ctgan | resolved by SDV (0.12.1 †) | Optional synthesizer. **BUSL-1.1** †. Requires torch. |
| torch (CPU) | `>=2.5` (CPU wheel, freeze exact) | Required by transformers 5.x (`torch>=2.5` †) and by CTGAN. The global 2.2.2 is too old. |
| transformers | `==5.17.0` † (or latest 4.x if 5.x conflicts; decided at M0) | CamelBERT NER. Requires Python ≥3.10 †. |
| huggingface-hub | resolved (`>=1.5,<2` †) | Model download at setup only. |
| scikit-learn | `1.8.0` (matches global) | TSTR models, NearestNeighbors for DCR. |
| scipy | `1.17.x` | KS test. |
| streamlit | `1.63.0` (matches global) | UI. |
| PyYAML | latest 6.x | Policy file. |
| SQLAlchemy | `2.0.52` + `psycopg[binary]` 3.x | **M8 only**. Goes in `requirements-postgres.txt`, not the MVP install. |
| pytest, hypothesis | latest | Tests. Hypothesis provides property tests for the offset map and format preservation. |
| reportlab | optional, M8 only | PDF. |

The NER model is `CAMeL-Lab/bert-base-arabic-camelbert-msa-ner`, **Apache-2.0** †. It is trained on ANERcorp (MSA) and loads via `pipeline("ner", ...)` †. Risk: Saudi dialect in the notes. The `-mix-ner` variant is the fallback candidate, and its license gets verified at M8 before use.

---

## 4. Data flow and function signatures
```
io.load_* ──► tables: dict[str, DataFrame]
   │
   ▼
profiling.profile_dataset(tables, db_fks=None) -> DatasetProfile
   │            (types, PKs, FKs; .to_sdv_metadata(exclude) -> sdv Metadata)
   ▼
detect.detect_columns(tables, prof) -> list[ColumnDetection]
detect.detect_free_text(tables, prof, ner: NameDetector) -> list[Span]
detect.baseline_spans(tables, prof) -> list[Span]            # demo comparison only
   │
   ▼
policy.load_policy(path) -> Policy
policy.resolve(policy, prof, detections, overrides) -> list[Decision]  # override wins, flagged
   │
   ├── mode=masked ──► transform.apply(tables, prof, decisions, spans, pseudo) -> twin
   │
   └── mode=synthetic ► synth.split_holdout(tables, prof, frac=.2, seed) -> (train, holdout)
                        synth.make_synthesizer(method) -> Synthesizer   # only synth.py imports sdv
                        s.fit(train, prof, exclude=direct_ids); twin = s.sample(scale, seed)
                        synth.fill_direct_ids(twin, decisions, rng, forbidden=originals)
                        synth.fill_text(twin, prof, rng)             # templates only
   ▼
evaluate.leak_scan(originals, twin, detector) -> LeakResult          # always
evaluate.privacy(train, twin, holdout, quasi_cols, mode) -> dict
evaluate.fidelity(train, twin, prof) -> dict                         # synthetic
evaluate.utility_tstr(train, twin, holdout, target, features) -> dict# synthetic
   ▼
report.build_report(run: RunResult, thresholds) -> dict ; report.write(report, out_dir)
```

Key signatures:
```python
# saudi_ids.py
Kind = Literal["SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"]
def normalize(text: str) -> tuple[str, list[int]]
def normalize_name(s: str) -> str
def canonical(kind: Kind, value: str) -> str      # HMAC input; e.g. mobile → "5XXXXXXXX" so 05…/+9665…/9665… agree
def is_valid_saudi_id(s: str) -> bool; is_valid_mobile; is_valid_iban; is_valid_email
def gen_saudi_id(rng: random.Random, first_digit: str | None = None) -> str
def gen_mobile(rng) -> str; gen_iban(rng) -> str
def gen_first_name(rng, gender: Literal["M","F"] | None) -> str; gen_family_name(rng) -> str
def name_gender(first: str) -> Literal["M","F"] | None   # from gazetteer
VALIDATORS: dict[Kind, Callable[[str], bool]]; GENERATORS: dict[Kind, Callable]

# types.py
@dataclass(frozen=True) class Span: table: str; row: int; column: str; start: int; end: int; type: Kind; confidence: float; source: str  # "regex+validator" | "ner" | "gazetteer"
@dataclass class ColumnDetection: table; column; tag: Tag; kind: Kind | None; score: float; valid_ratio: float; name_hint: bool; needs_review: bool

# ner.py
class NameDetector(Protocol):
    def find(self, text: str) -> list[tuple[int, int, float]]
class CamelNER: ...        # lazy load, local files only, time budget → raises NERUnavailable
class GazetteerNER: ...    # normalize_name tokens against first-name list (+ following family-name token)

# transform.py
class Pseudonymizer:
    def __init__(self, key: bytes, forbidden: dict[Kind, set[str]]): ...
    def prepare(self, values: dict[Kind, set[str]]) -> None   # builds mapping over SORTED canonical values → order-independent collisions
    def fake(self, kind: str, value: str, **opts) -> str
def render_like(original: str, fake_ascii: str, kind: Kind) -> str   # digit script, separator positions, prefix style
def replace_spans(text: str, spans: list[Span], pseudo: Pseudonymizer) -> str   # end→start
def generalize(series: pd.Series, rule: dict) -> pd.Series
def apply(tables, prof, decisions, spans, pseudo) -> dict[str, pd.DataFrame]

# synth.py: the seam that lets SDV (BUSL) be swapped for our own scipy copula later
class Synthesizer(Protocol):
    name: str; license: str                       # written into the report
    def fit(self, tables: dict[str, pd.DataFrame], prof: DatasetProfile, exclude: set[tuple[str, str]]) -> None
    def sample(self, scale: float = 1.0, seed: int | None = None) -> dict[str, pd.DataFrame]
class SdvGaussianCopula: ...   # adapter; builds sdv Metadata from DatasetProfile internally
class SdvHMA: ...              # M8
def make_synthesizer(method: Literal["gaussian_copula", "ctgan", "hma"]) -> Synthesizer
# profiling.py stays SDV-free; DatasetProfile → sdv Metadata conversion lives in the adapter.

# config.py
def load_key() -> bytes          # NAZEER_KEY, require ≥32 chars; never logged/written

# pipeline.py (CLI)
def run(src: InputSpec, mode: Literal["masked","synthetic"], policy_path: Path,
        overrides: dict, out_dir: Path, target: str | None = None) -> RunResult
# python -m nazeer.pipeline --csv data/demo --mode masked --out out/ [--target is_large_claim]
```

Detection details that go beyond the spec:
- **Name hints** apply only when the column name itself matches (for example `national_id`). A bare `id` hint alone scores 0.2, which is NORMAL, so plain PK columns are not tagged DIRECT_ID.
- **`valid_ratio` for names** is the share of values whose first token is in the gazetteer. For email it is the share matching a regex.
- **Free-text confidence** starts from the validator pass. It is lowered when a context word like فاتورة, طلب or رقم الطلب appears within about 3 tokens before the number, because about 10% of random 10-digit numbers pass the ID checksum by chance.

---

## 5. Test plan (mapped to the spec)
| Spec item | Test |
|---|---|
| Validators on vectors | `test_saudi_ids.py::test_id_vectors`, `test_iban_vector`, and mobile formats (`05`, `+9665`, `9665`, with negative cases) |
| Generators ×1,000 pass | One parametrized test per generator, including `first_digit` preservation |
| Determinism ×100 and across 2 processes | In-process loop. Plus `subprocess.run([sys.executable, -c ...])` twice with different `PYTHONHASHSEED`, then compare outputs |
| Offset map | Fixed cases (`٠٥٠ ٣٣١ ٨٨٤٢`, mixed `۱۲۳` and Latin, text with tashkeel) plus a Hypothesis property: `orig[offset_map[i]]` normalizes to `norm[i]` for every i, and the map is monotonic |
| Format preservation | Arabic-Indic spaced mobile → output stays Arabic-Indic with spaces at the same digit positions. `+966` stays `+966`. IBAN keeps its groups of 4 |
| Referential integrity | After transform, set(claims.customer_id) ⊆ set(customers.customer_id), with the same join cardinality as the original |
| Detection recall/precision | `test_detect.py` scores against `golden_labels.csv` and asserts identifier recall ≥ 0.90. It prints per-type P/R for both the baseline and Nazeer, and a hard-negative false-positive count |
| Leak scan | Demo masked run gives an empty leak scan. The test then injects one original ID into a twin note (in Arabic-Indic digits with spaces) and asserts the verdict is FAIL |
| Extra | No-raw-values-in-logs: run the pipeline with a log capture and assert that no original identifier appears in the captured output. `load_key` refuses a missing or short key |

---

## 6. Risks and mitigations
**Technical**
- **Dependency conflicts.** Global pandas 3 and torch 2.2 conflict with SDV and transformers. Mitigation: a dedicated venv and a lock file, both in M0.
- **Leak scan fails from chance collisions.** There are about 2×10⁸ valid IDs. 5k fakes against 5k reals gives an expected ~0.1 collisions per run, so about 1 run in 10 would fail on its own. Mitigation: every generator (HMAC and 5b fill) rejects outputs that are in the set of **original** values and rehashes with a counter. The same applies to mobiles.
- **Collision rehash vs determinism.** Resolving collisions "in processing order" makes the output depend on order. Mitigation: `prepare()` builds the in-memory mapping over the sorted unique canonical values of the whole run, and the mapping is never persisted. Across *different* datasets, a collision could still resolve differently. The probability is about 10⁻⁸ per pair, which we document.
- **Space-merging glues separate numbers.** For example `رقم 12 1098765432`. Mitigation: merge only runs whose groups look like phone, ID or IBAN groupings (group sizes 2–4, total length 9–24), keep the unmerged candidates as well, and let the validator decide.
- **Name consistency across column and text.** The column holds a full name while the text may mention only a first name. Mitigation: pseudonymize **per token**, with first name → fake first name of the same gender (gender from the gazetteer) and family → fake family, keyed on `normalize_name(token)`.
- **The detector cannot catch what it missed.** Rerunning it on the twin misses the same items. Mitigation: the leak scan also runs an exhaustive normalized substring search for **every known original identifier** (structured columns plus detected spans) over every twin cell. Identifiers that appear only in free text and were missed there remain a documented residual, measured through golden-label recall.
- **NER is slow or weak on dialect.** Mitigation: lazy load, a batch time budget, and a gazetteer fallback. Both are compared on golden labels.
- **HMA scope.** The docs say it is "optimized for ~5 tables, 1 level of depth". That fits the demo. The UI warns on larger schemas.

**Data / privacy**
- **Raw values leaking through logs.** Tracebacks, pandas errors and SDV warnings can print values. Mitigation: a `safe_log` filter, a top-level exception wrapper that logs only type/table/column, and SDV warnings routed through the filter. **Unkeyed hashes of IDs are brute-forceable** (a space of only about 10⁹), so logs never contain per-value hashes, only counts. "Hashes" in the spec is interpreted as the policy/config hash.
- **Hidden network traffic.** Mitigation: Streamlit `gatherUsageStats=false`, `HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`. M0 checks SDV for any usage telemetry or local log files and disables them.
- **Streamlit caching.** It must never use `persist="disk"`. The UI shows originals only in session memory.
- **Privacy metrics depend on the mode.** In 5a, rows are the same people, so DCR is meaningless and "0 exact copies" holds only because IDs changed. 5a reports k-anonymity plus the leak scan. 5b reports exact copies, DCR and the leak scan.
- **k-anonymity on the demo.** With age bins × city × gender, k < 5 is likely. The report states the original FAIL plainly. `kanon.suggest_fixes` proposes generalization or suppression with before/after k. The user applies a fix in the UI (or with `--apply-fix` in the CLI), and the report records both the original FAIL and the applied fix.
- **Windows.** All paths use `pathlib`, and all files are read and written with `encoding="utf-8"` explicitly, because the Windows default codepage corrupts Arabic. Docs use PowerShell syntax. Subprocess tests use `sys.executable`.

**Legal assumptions (not legal advice)**
- A generated ID is format-valid and may equal a real person's ID outside our data. The report says so.
- The masked twin 5a is likely still personal data under PDPL: each row maps to a real person, the key exists, and with the key an ID can be recovered by enumeration. 5b is stronger but not proven anonymous. The report never claims "anonymous".
- **SDV and CTGAN are BUSL-1.1.** The Additional Use Grant forbids using them "for a Synthetic Data Service", and the change to MIT happens 4 years after each release. A hackathon demo run by the data owner is fine. **Commercializing Nazeer as a service would need a DataCebo license** or our own Gaussian-copula implementation using scipy. The `Synthesizer` protocol keeps that swap to one new adapter class; the replacement is not built now. **Verified at M0: copulas and rdt are BUSL-1.1 as well**, so a replacement must use scipy/numpy directly. Also verified: SDV has no seed parameter and seeds itself internally (identical samples across fits); the report records "seed: fixed by SDV". The report records the synthesizer name and license. SDMetrics is MIT and CamelBERT is Apache-2.0.
- Detection is never complete. The UI always shows a "needs human review" queue and never claims full coverage.

---

## 7. Decisions (approved) and remaining open questions
**Decided:**
1. **Name leak scan.** Hard-fail on SAUDI_ID, MOBILE, IBAN and EMAIL. For names, hard-fail if any 5a row keeps its own original full name. In 5b, the full-name overlap rate is reported as information only.
2. **Age bins.** Width is 10 years.
3. **Demo schema.** No `birth_date` or `nationality` columns in the demo. Both stay in `policy.yaml` as inactive examples, and the policy engine skips rules whose column is absent (logged as a count only).
4. **DCR rule.** PASS if median DCR(twin→train) ≥ median DCR(holdout→train). The report also gives the share of twin rows closer to train than to holdout.
5. **Output.** CSV folder only, never written back to any DB. PostgreSQL input moves to M8.
6. **TSTR.** Target is `is_large_claim` (amount > P90), with LR + RF. `max_utility_drop` is an absolute AUC drop.
7. **k-anonymity.** Optional suggestion step (see `kanon.py`).
8. **Repo.** `Desktop\nazeer\`, local git only. The user adds the remote later.

**Still open:**
- **Deadline and team size.** These were left as placeholders in the approval. The cut line is `cumulative hours ≤ team × usable hours` in the milestone table and gets marked once they're known.

---

## 8. What we will NOT build
- Auth, multi-user, roles, a job queue, microservices, Docker orchestration.
- Input sources other than a CSV folder (MVP) and PostgreSQL (stretch), and no writing back to databases.
- Our own scipy Gaussian-copula replacement for SDV. Only the `Synthesizer` seam is built now.
- Training any model from scratch, or fine-tuning NER.
- Persisted pseudonym mapping tables or any re-identification ("unmask") feature.
- Differential-privacy guarantees or formal anonymity claims.
- Detection of addresses, medical codes, or IDs from other countries beyond the listed types (email is included).
- Synthetic free text from an LLM. 5b text comes from templates only.
- Multi-table schemas beyond what HMA handles comfortably (about 5 tables, depth 1).

## Verification (end-to-end, PowerShell)
```powershell
cd $HOME\Desktop\nazeer
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
python -m data_gen.make_demo_data --seed 42 --n 3000
$env:NAZEER_KEY = "<at least 32 random characters>"
python -m nazeer.pipeline --csv data\demo --mode masked --out out\masked        # expect: leak scan empty, verdict in out\masked\report.json
python -m nazeer.pipeline --csv data\demo --mode synthetic --target is_large_claim --out out\synth
streamlit run nazeer\app.py
Select-String -Path out\*\*.log -Pattern (Import-Csv data\demo\customers.csv).national_id -SimpleMatch   # expect: no matches
```
