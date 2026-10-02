"""Every supported way of writing an identifier must get a VALID fake, in the same layout."""
import random

import pytest

from nazeer import saudi_ids as s
from nazeer.transform import Pseudonymizer

AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _ids():
    v = s.gen_saudi_id(random.Random(1), "1")
    return [v, v.translate(AR), v.translate(FA), f"{v[0]} {v[1:4]} {v[4:7]} {v[7:]}", f"{v[:4]}-{v[4:7]}-{v[7:]}",
            f"{v[:3]}.{v[3:6]}.{v[6:]}", s.gen_saudi_id(random.Random(2), "2")]


def _mobiles():
    m = "0585472803"
    return [m, m.translate(AR), f"{m[:3]} {m[3:6]} {m[6:]}", f"{m[:3]}-{m[3:6]}-{m[6:]}", f"({m[:3]}) {m[3:6]} {m[6:]}",
            f"({m[:3]}) {m[3:6]} {m[6:]}".translate(AR), "+966" + m[1:], f"+966 {m[1:3]} {m[3:6]} {m[6:]}",
            "966" + m[1:], "00966" + m[1:], f"{m[:3]}.{m[3:6]}.{m[6:]}"]


def _ibans():
    v = "SA0380000000608010167519"
    return [v, v.lower(), " ".join(v[i:i + 4] for i in range(0, 24, 4)), "SA " + v[2:], v[:2] + v[2:].translate(AR)]


@pytest.mark.parametrize("kind,raw", [("SAUDI_ID", r) for r in _ids()] + [("MOBILE", r) for r in _mobiles()]
                         + [("IBAN", r) for r in _ibans()])
def test_fake_is_valid_and_keeps_the_layout(kind, raw):
    assert s.is_valid(kind, raw), raw  # the original itself is a supported format
    fake = Pseudonymizer(b"layout-test-key-0123456789abcdef").value(kind, raw)
    assert s.is_valid(kind, fake), (raw, fake)
    assert s.canonical(kind, fake) != s.canonical(kind, raw)
    same_layout = [c for c in raw if not c.isdigit() and s.ascii_digit(c) is None] == \
        [c for c in fake if not c.isdigit() and s.ascii_digit(c) is None]
    assert same_layout or kind == "IBAN", (raw, fake)
