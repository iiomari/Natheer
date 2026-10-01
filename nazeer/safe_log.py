"""Logging that never emits raw data values.

Discipline comes first: log only counts, table/column names and types. This
module is the safety net behind that discipline:

* Every handler gets a RedactingFilter that masks long digit runs (ASCII,
  Arabic-Indic and Persian digits, with or without spaces/hyphens/dots),
  IBAN-like strings and email addresses.
* Exception messages are dropped (they often quote the offending value, e.g.
  pandas "could not convert '1110704341'"); only the exception type and the
  stack frames (file:line in function) are kept.
* Python warnings are routed through the same filtered handlers.

Person names cannot be caught by a regex, so never pass cell values to a
logger. Column names are allowed and are left intact, Arabic included.
"""
from __future__ import annotations

import logging
import re
import sys
import traceback
from pathlib import Path
from types import TracebackType
from typing import IO

REDACTED = "<redacted>"

# In str patterns \d and \s are Unicode-aware, so Arabic-Indic (U+0660..0669)
# and Persian (U+06F0..06F9) digits are covered without translation.
_IBAN = re.compile(r"SA\d{2}(?:[\s-]?[0-9A-Za-z]){20}", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LONG_DIGITS = re.compile(r"\+?\d(?:[\s.\-]?\d){6,}")

_HANDLER_MARK = "_nazeer_handler"


def redact(text: str) -> str:
    text = _IBAN.sub(REDACTED, text)
    text = _EMAIL.sub(REDACTED, text)
    return _LONG_DIGITS.sub(REDACTED, text)


def _frames(tb: TracebackType | None) -> str:
    return " <- ".join(
        f"{Path(f.filename).name}:{f.lineno} in {f.name}"
        for f in reversed(traceback.extract_tb(tb))
    )


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # bad format args; never fall back to printing them
            message = str(record.msg)
        if record.exc_info and record.exc_info[0] is not None:
            etype, _, tb = record.exc_info
            message = f"{message} [{etype.__name__}; message suppressed; at {_frames(tb)}]"
        record.msg = redact(message)
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def configure_logging(
    level: int | str = logging.INFO,
    log_file: Path | None = None,
    stream: IO[str] | None = None,
) -> None:
    """Install filtered handlers on the root logger (idempotent)."""
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, _HANDLER_MARK, False):
            root.removeHandler(h)
            h.close()

    handlers: list[logging.Handler] = [logging.StreamHandler(stream or sys.stderr)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for h in handlers:
        h.addFilter(RedactingFilter())
        h.setFormatter(fmt)
        setattr(h, _HANDLER_MARK, True)
        root.addHandler(h)
    root.setLevel(level)
    logging.captureWarnings(True)


# SDV loggers. Off by default (log_registry: null in sdv_logger_config.yml),
# but a user-level config can switch them to a CSV FileHandler with
# propagate=False, which would bypass our filter.
SDV_LOGGERS = ("SingleTableSynthesizer", "MultiTableSynthesizer", "SingleTableMetadata", "MultiTableMetadata")


def route_library_loggers(names: tuple[str, ...] = SDV_LOGGERS) -> None:
    """Strip a library's own handlers so its records reach our filtered root handlers.

    Call after constructing an SDV synthesizer (SDV attaches handlers lazily).
    """
    for name in names:
        lib_logger = logging.getLogger(name)
        for h in list(lib_logger.handlers):
            lib_logger.removeHandler(h)
            h.close()
        lib_logger.propagate = True


def install_excepthook() -> None:
    """For the CLI: uncaught errors print type and frames only, never the message."""

    def hook(etype: type[BaseException], value: BaseException, tb: TracebackType | None) -> None:
        logging.getLogger("nazeer").error("run failed", exc_info=(etype, value, tb))

    sys.excepthook = hook
