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
| M4 Policy + transform | done | (this commit) |
| M5 Evaluation + report + k-anon backend | not started | — |
| M6a Minimal Streamlit flow | not started | — |
| M7 Synthetic 5b + fidelity + TSTR + DCR | not started | — |
| M6b UI polish + overrides + k-anon apply | not started | — |
| M8 Stretch (NER, HMA, PDF, Postgres) | not started | — |

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

## Known issues

(none yet)

## Next step

M5: leak scan, exact copies, DCR, k-anonymity + suggestions, JSON report, pipeline CLI.
