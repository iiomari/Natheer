"""Shared data types. Kept dependency-free to avoid circular imports."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from nazeer.saudi_ids import Kind

Tag = Literal["DIRECT_ID", "QUASI_ID", "SENSITIVE", "NORMAL", "FREE_TEXT"]
ColType = Literal["numeric", "categorical", "date", "short_text", "free_text"]
Tables = dict  # dict[str, pandas.DataFrame]; alias kept loose so this module needs no pandas


@dataclass(frozen=True)
class Span:
    """A detected (or planted) identifier inside a free-text cell. Offsets index the ORIGINAL text."""
    table: str
    row: int  # positional row index
    column: str
    start: int
    end: int
    type: Kind
    confidence: float
    source: str  # "regex+validator" | "gazetteer" | "ner" | "baseline"


@dataclass
class ColumnProfile:
    table: str
    column: str
    dtype: ColType
    n_rows: int
    n_null: int
    n_unique: int
    mean_len: float
    arabic_ratio: float
    is_primary_key: bool = False


@dataclass(frozen=True)
class ForeignKey:
    child_table: str
    child_column: str
    parent_table: str
    parent_column: str
    containment: float


@dataclass
class TableProfile:
    name: str
    n_rows: int
    columns: dict[str, ColumnProfile]
    primary_key: str | None


@dataclass
class DatasetProfile:
    tables: dict[str, TableProfile]
    foreign_keys: list[ForeignKey] = field(default_factory=list)

    def column(self, table: str, column: str) -> ColumnProfile:
        return self.tables[table].columns[column]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ColumnDetection:
    table: str
    column: str
    tag: Tag
    kind: Kind | None
    score: float
    valid_ratio: float
    name_hint: bool
    needs_review: bool
    reason: str
    human_override: bool = False
