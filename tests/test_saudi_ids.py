import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nazeer import saudi_ids as s

# ------------------------------------------------------------------ validators

@pytest.mark.parametrize("value", ["1110704341", "1909266858", "2129040479"])
def test_valid_id_vectors(value):
    assert s.is_valid_saudi_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "1234567890", "2111111111",  # spec vectors: bad checksum
        "3110704341",                # wrong first digit
        "111070434", "11107043410",  # wrong length
        "١١١٠٧٠٤٣٤١",                # Arabic-Indic: must be normalized first
        "111070434a", "",
    ],
)
def test_invalid_ids(value):
    assert not s.is_valid_saudi_id(value)


@pytest.mark.parametrize("value", ["0503318842", "+966503318842", "966503318842", "00966503318842"])
def test_valid_mobiles(value):
    assert s.is_valid_mobile(value)


@pytest.mark.parametrize(
    "value", ["0603318842", "050331884", "05033188421", "+96650331884", "+966603318842", "٠٥٠٣٣١٨٨٤٢"]
)
def test_invalid_mobiles(value):
    assert not s.is_valid_mobile(value)


def test_iban_vector():
    assert s.is_valid_iban("SA0380000000608010167519")


@pytest.mark.parametrize(
    "value",
    [
        "SA0380000000608010167518",       # one digit changed
        "SA038000000060801016751",        # 23 chars
        "SA03 8000 0000 6080 1016 7519",  # not canonical
        "GB0380000000608010167519",
    ],
)
def test_invalid_ibans(value):
    assert not s.is_valid_iban(value)


def test_email():
    assert s.is_valid_email("a.b+c@example.com")
    assert not s.is_valid_email("not-an-email")


def test_known_name():
    assert s.is_known_name("محمد العتيبي")
    assert s.is_known_name("احمد")  # spelling variant of أحمد
    assert not s.is_known_name("فاتورة")


# ------------------------------------------------------------------ generators

N = 1000


@pytest.mark.parametrize("kind", ["SAUDI_ID", "MOBILE", "IBAN", "EMAIL", "PERSON_NAME"])
def test_generators_pass_their_validator(kind):
    rng = random.Random(7)
    gen, valid = s.GENERATORS[kind], s.VALIDATORS[kind]
    bad = [v for v in (gen(rng) for _ in range(N)) if not valid(v)]
    assert not bad, f"{len(bad)} invalid {kind} outputs"


@pytest.mark.parametrize("first", ["1", "2"])
def test_id_first_digit_preserved(first):
    rng = random.Random(1)
    for _ in range(N):
        v = s.gen_saudi_id(rng, first_digit=first)
        assert v[0] == first and s.is_valid_saudi_id(v)


def test_iban_bank_code_preserved():
    rng = random.Random(1)
    for _ in range(N):
        v = s.gen_iban(rng, bank_code="80")
        assert v[4:6] == "80" and s.is_valid_iban(v)


@pytest.mark.parametrize("gender", ["M", "F"])
def test_names_are_gender_aware(gender):
    rng = random.Random(3)
    for _ in range(N):
        first, family = s.gen_person_name(rng, gender).split(" ")
        assert s.name_gender(first) == gender
        assert s.is_family_name(family)


def test_generators_are_seed_deterministic():
    def draw(seed):
        rng = random.Random(seed)
        return [s.GENERATORS[k](rng) for k in s.GENERATORS for _ in range(20)]

    assert draw(42) == draw(42)
    assert draw(42) != draw(43)


# --------------------------------------------------------------- normalization

def test_spec_example():
    norm, offsets = s.normalize("٠٥٠ ٣٣١ ٨٨٤٢")
    assert norm == "0503318842"
    assert offsets == [0, 1, 2, 4, 5, 6, 8, 9, 10, 11]


def test_mixed_arabic_sentence_maps_back():
    text = "رقم جوالي ٠٥٠-٣٣١-٨٨٤٢ وهويتي ۱۱۱۰۷۰۴۳۴۱ شكرا"
    norm, offsets = s.normalize(text)
    for target in ("0503318842", "1110704341"):
        start = norm.index(target)
        o_start, o_end = s.to_original_span(offsets, start, start + len(target))
        original = text[o_start:o_end]
        assert s.normalize(original)[0] == target
        # the span is tight: no surrounding letters or spaces
        assert s.ascii_digit(original[0]) and s.ascii_digit(original[-1])


def test_iban_with_spaces_is_joined():
    norm, _ = s.normalize("الآيبان SA03 8000 0000 6080 1016 7519 للتحويل")
    assert "SA0380000000608010167519" in norm


def test_space_between_digit_and_word_is_kept():
    assert s.normalize("عمره 35 سنة")[0] == "عمره 35 سنة"


def test_decimal_dot_is_joined_as_specified():
    # Spec: dots inside digit runs are removed. Validators then reject most such
    # merged numbers, which is why every candidate must pass a validator.
    assert s.normalize("1500.50")[0] == "150050"


def test_long_separator_run_breaks_number():
    assert s.normalize("050    331")[0] == "050    331"
    assert s.normalize("050 - 331")[0] == "050331"


def test_bidi_marks_inside_number_are_removed():
    assert s.normalize("050‏331‎8842")[0] == "0503318842"


_ALPHABET = st.sampled_from(
    list("0123456789")
    + [chr(0x0660 + d) for d in range(10)]
    + [chr(0x06F0 + d) for d in range(10)]
    + list("محمدالعتيبيSAab")
    + [" ", "-", ".", " ", "‏", "\n", ","]
)


@given(st.lists(_ALPHABET, max_size=80).map("".join))
def test_offset_map_properties(text):
    norm, offsets = s.normalize(text)
    assert len(norm) == len(offsets)
    assert offsets == sorted(set(offsets))  # strictly increasing
    for i, o in enumerate(offsets):
        assert (s.ascii_digit(text[o]) or text[o]) == norm[i]
    dropped = set(range(len(text))) - set(offsets)
    assert all(text[i] in s._SEPARATORS for i in dropped)
    assert s.normalize(norm)[0] == norm  # idempotent


def test_to_original_span_rejects_bad_range():
    _, offsets = s.normalize("12345")
    with pytest.raises(ValueError):
        s.to_original_span(offsets, 3, 3)


# ------------------------------------------------------------------ names, canonical

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("أحمد", "احمد"),
        ("إبراهيم", "ابراهيم"),
        ("آمنة", "امنه"),
        ("مُحَمَّد", "محمد"),
        ("محـــمد", "محمد"),
        ("مصطفى", "مصطفي"),
        ("  نورة   العتيبي ", "نوره العتيبي"),
    ],
)
def test_normalize_name(raw, expected):
    assert s.normalize_name(raw) == expected


def test_mobile_formats_share_canonical_form():
    forms = ["0503318842", "+966503318842", "966503318842", "00966503318842",
             "٠٥٠ ٣٣١ ٨٨٤٢", "+966 50 331 8842"]
    assert {s.canonical("MOBILE", f) for f in forms} == {"503318842"}


def test_canonical_id_and_iban():
    assert s.canonical("SAUDI_ID", "١١١ ٠٧٠ ٤٣٤١") == "1110704341"
    assert s.canonical("IBAN", "sa03 8000 0000 6080 1016 7519") == "SA0380000000608010167519"


@pytest.mark.parametrize(
    "kind, raw",
    [
        ("MOBILE", "٠٥٠ ٣٣١ ٨٨٤٢"),
        ("MOBILE", "+966 50 331 8842"),
        ("SAUDI_ID", "١١١-٠٧٠-٤٣٤١"),
        ("IBAN", "sa03 8000 0000 6080 1016 7519"),
        ("EMAIL", " a@example.com "),
    ],
)
def test_is_valid_accepts_any_spelling(kind, raw):
    assert s.is_valid(kind, raw)


@pytest.mark.parametrize("kind, raw", [("MOBILE", "503318842"), ("MOBILE", "٠٦٠ ٣٣١ ٨٨٤٢"), ("SAUDI_ID", "١٢٣٤٥٦٧٨٩٠")])
def test_is_valid_rejects(kind, raw):
    assert not s.is_valid(kind, raw)
