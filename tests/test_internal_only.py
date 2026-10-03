"""Internal presentation material stays internal (docs/internal/ only, not tracked)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"criteri|judg|weight|rubric|scoring sheet|معايير|معيار|التحكيم|وزن|أوزان", re.IGNORECASE)
PUBLIC = ["README.md", "nazeer/app.py", "nazeer/ui_logic.py", "nazeer/report.py", "nazeer/pipeline.py",
          "data/human_notes_TEMPLATE.csv"]


def public_files():
    yield from (ROOT / rel for rel in PUBLIC)
    for path in (ROOT / "docs").rglob("*.md"):
        if "internal" not in path.relative_to(ROOT / "docs").parts:
            yield path
    yield from (ROOT / "nazeer_api").rglob("*.py")


def test_no_internal_terms_in_public_files():
    for path in public_files():
        if path.exists():
            hits = FORBIDDEN.findall(path.read_text(encoding="utf-8-sig"))
            assert not hits, f"{path.relative_to(ROOT)} mentions {sorted(set(hits))}"


def test_no_internal_terms_in_generated_reports():
    for report in (ROOT / "out").glob("**/report.json"):
        assert not FORBIDDEN.search(report.read_text(encoding="utf-8")), report
