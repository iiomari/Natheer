import io
import logging
import warnings

import pytest

from nazeer.safe_log import REDACTED, configure_logging, redact

SECRETS = [
    "1110704341",                  # Saudi ID
    "٠٥٠ ٣٣١ ٨٨٤٢",                # mobile, Arabic-Indic with spaces
    "۰۵۰۳۳۱۸۸۴۲",                  # mobile, Persian digits
    "+966 50 331 8842",
    "SA03 8000 0000 6080 1016 7519",
    "SA0380000000608010167519",
    "someone@example.com",
]


@pytest.fixture
def log_stream():
    stream = io.StringIO()
    configure_logging(stream=stream)
    yield stream
    configure_logging()  # restore default stderr handler


@pytest.mark.parametrize("secret", SECRETS)
def test_redact_masks_identifier(secret):
    out = redact(f"value was {secret} here")
    assert secret not in out
    assert REDACTED in out


def test_redact_keeps_counts_and_column_names():
    msg = "table=customers column=الاسم type=PERSON_NAME rows=4500"
    assert redact(msg) == msg


@pytest.mark.parametrize("secret", SECRETS)
def test_logger_args_are_redacted(log_stream, secret):
    logging.getLogger("nazeer.test").info("found %s in column %s", secret, "notes")
    out = log_stream.getvalue()
    assert secret not in out
    assert "notes" in out


def test_exception_message_is_suppressed(log_stream):
    try:
        int("1110704341x")
    except ValueError:
        logging.getLogger("nazeer.test").exception("cast failed for column %s", "national_id")
    out = log_stream.getvalue()
    assert "1110704341" not in out
    assert "ValueError" in out
    assert "national_id" in out


def test_warnings_are_routed_and_redacted():
    # pytest swaps warnings.showwarning when the test body starts, so the
    # routing must be installed here rather than in a fixture.
    stream = io.StringIO()
    logging.captureWarnings(False)
    configure_logging(stream=stream)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            warnings.warn("odd value 0503318842 in column mobile")
    finally:
        configure_logging()
    out = stream.getvalue()
    assert "0503318842" not in out
    assert "mobile" in out


def test_library_file_handlers_are_rerouted(log_stream, tmp_path):
    from nazeer.safe_log import route_library_loggers

    lib = logging.getLogger("SingleTableSynthesizer")
    side_file = tmp_path / "sdv_logs.csv"
    lib.addHandler(logging.FileHandler(side_file, encoding="utf-8"))
    lib.propagate = False

    route_library_loggers()
    lib.warning("fit on value 1110704341")

    assert not lib.handlers and lib.propagate
    assert side_file.read_text(encoding="utf-8") == ""
    out = log_stream.getvalue()
    assert "1110704341" not in out and REDACTED in out
