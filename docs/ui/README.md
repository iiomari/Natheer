# UI screenshots

`before-*` show the previous single-page English UI (captured 2026-10-01, before the redesign).
`after-*` show the redesigned four-step Arabic UI on the full demo (seed 42, 3,000 customers), at
1600 px wide, in demo mode (no key typed).

| Step | Before | After |
|---|---|---|
| Start | `before-1-data.png` | `after-0-start.png`, `after-0-start-dark.png` |
| 1 · Data | `before-1-data.png` | `after-1-data.png`, `after-1-data-dark.png` |
| 2 · Detection | `before-2-detection.png` | `after-2-detection.png`, `after-2-detection-dark.png` |
| 3 · Twin | `before-3-4-twin-and-evidence.png` | `after-3-before-generate.png`, `after-3-twin.png` |
| 4 · Proof | `before-3-4-twin-and-evidence.png` | `after-4-proof-k-fail.png`, `after-4-proof-pass.png`, `after-4-planted-leak.png` |
| Why it works | `before-why-it-works.png` | `after-why-it-works.png` |
| Try your text | (did not exist) | `after-try-your-text.png` |

Regenerate the `after-*` files (Playwright is a documentation tool only, not a project dependency):

```powershell
streamlit run nazeer\app.py --server.port 8601 --server.headless true
python scripts\ui_screenshots.py --url http://localhost:8601 --out docs\ui --dark
```

What to check by eye on a projector:
- Spaced Arabic-digit numbers keep their group order, e.g. `+٩٦٦ ٥٠ ٥٦٤ ٢٠٢٤`, never reversed.
- Every highlight has a text label next to its color.
- The tracked customer is the same in steps 1-3.
- Step 4 goes FAIL (k = 1) → "apply the suggested fix" → PASS (k = 1 → 5); "plant a leak" turns the leak
  card to FAIL and "remove" restores it.
