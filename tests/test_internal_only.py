"""Judging criteria and their weights are internal only (docs/internal/ only)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"criteri|judg|weight|rubric|scoring sheet|معايير|معيار|التحكيم|وزن|أوزان", re.IGNORECASE)
JUDGE_FACING = ["README.md", "nazeer/app.py", "nazeer/ui_logic.py", "nazeer/report.py", "nazeer/pipeline.py",
                "docs/HOW_TO_WRITE_NOTES.md", "data/human_notes_TEMPLATE.csv"]


def test_no_criteria_or_weights_in_judge_facing_files():
    for rel in JUDGE_FACING:
        path = ROOT / rel
        if path.exists():
            hits = FORBIDDEN.findall(path.read_text(encoding="utf-8-sig"))
            assert not hits, f"{rel} mentions {sorted(set(hits))}"


def test_no_criteria_in_generated_reports():
    for report in (ROOT / "out").glob("**/report.json"):
        assert not FORBIDDEN.search(report.read_text(encoding="utf-8")), report
