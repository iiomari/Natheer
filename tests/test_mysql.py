"""MySQL input/output.

Unit tests run everywhere. Integration tests need a running MySQL server and real
credentials (NAZEER_MYSQL_* or .env); until then they are skipped with the reason.
Integration tests only create and drop databases named nazeer_test_*.
"""
import datetime as dt
import decimal
import json
import secrets

import pandas as pd
import pytest

from nazeer import mysqlio
from nazeer.models import ForeignKey

ENV_KEYS = ("NAZEER_MYSQL_HOST", "NAZEER_MYSQL_PORT", "NAZEER_MYSQL_USER", "NAZEER_MYSQL_PASSWORD")


@pytest.fixture
def clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def _env_file(tmp_path, password):
    f = tmp_path / ".env"
    f.write_text(f"NAZEER_MYSQL_HOST=dbhost\nNAZEER_MYSQL_PORT=3307\nNAZEER_MYSQL_USER=u1\n"
                 f"NAZEER_MYSQL_PASSWORD={password}\n", encoding="utf-8")
    return f


# ------------------------------------------------------------------ settings (no server)

def test_placeholder_password_means_waiting(clean_env, tmp_path):
    with pytest.raises(mysqlio.CredentialsPending):
        mysqlio.load_settings(_env_file(tmp_path, "CHANGE_ME"))


def test_env_file_is_read_and_real_env_wins(clean_env, tmp_path):
    clean_env.setenv("NAZEER_MYSQL_USER", "from_env")
    s = mysqlio.load_settings(_env_file(tmp_path, "pw-from-file"))
    assert (s.host, s.port, s.user, s.password) == ("dbhost", 3307, "from_env", "pw-from-file")


def test_empty_password_is_allowed(clean_env, tmp_path):
    assert mysqlio.load_settings(_env_file(tmp_path, "")).password == ""


def test_credentials_never_appear_in_repr(clean_env, tmp_path):
    s = mysqlio.load_settings(_env_file(tmp_path, "s3cret-pw"))
    for text in (repr(s), str(s), f"{s}"):
        assert "s3cret-pw" not in text and "u1" not in text and "dbhost" not in text


# ------------------------------------------------------------------ target safety (no server)

@pytest.mark.parametrize("source, target", [("prod", "prod"), ("Prod", "pROD"), (None, "mysql"),
                                            ("prod", "information_schema"), ("prod", "dev; DROP"), ("prod", "")])
def test_unsafe_targets_are_refused(source, target):
    with pytest.raises(mysqlio.UnsafeTarget):
        mysqlio.check_target(source, target)


def test_separate_target_is_accepted():
    assert mysqlio.check_target("nazeer_prod_demo", "nazeer_dev") == "nazeer_dev"


def test_write_to_source_is_refused_before_connecting():
    dummy = mysqlio.MySQLSettings("unreachable.invalid", 1, "nobody", "x")
    with pytest.raises(mysqlio.UnsafeTarget):
        mysqlio.write_twin(dummy, {"t": pd.DataFrame({"a": ["1"]})}, "nazeer_prod_demo", source_db="NAZEER_PROD_DEMO")


def test_cli_refuses_same_target_before_any_work(clean_env, tmp_path):
    from nazeer import pipeline

    clean_env.setenv("NAZEER_MYSQL_PASSWORD", "dummy")
    with pytest.raises(mysqlio.UnsafeTarget):
        pipeline.main(["--mysql-db", "nazeer_prod_demo", "--mysql-target", "nazeer_prod_demo", "--out", str(tmp_path)])


# ------------------------------------------------------------------ type mapping (no server)

@pytest.mark.parametrize("values, source_type, expected", [
    (["1", "22"], "int", "int"),
    (["30-39", "40-49"], "int", "VARCHAR(32)"),              # generalized ages no longer fit INT
    (["2024-03-15"], "date", "date"),
    (["2024-03"], "date", "VARCHAR(32)"),                    # generalized to month
    (["12.50", "3"], "decimal(12,2)", "decimal(12,2)"),
    (["مرحبا بالعالم"], "varchar(5)", "VARCHAR(32)"),          # too long for the source column
    (["x" * 300], None, "TEXT"),
    (["100001", "100002"], None, "BIGINT"),
])
def test_target_column_type(values, source_type, expected):
    assert mysqlio.target_column_type(pd.Series(values), source_type) == expected


def test_value_conversion_to_text():
    assert mysqlio._to_text(decimal.Decimal("12.50")) == "12.50"
    assert mysqlio._to_text(dt.date(2024, 3, 15)) == "2024-03-15"
    assert mysqlio._to_text(dt.datetime(2024, 3, 15, 8, 30)) == "2024-03-15 08:30:00"
    assert mysqlio._to_text("نص عربي".encode()) == "نص عربي"
    assert mysqlio._to_text(None) is None and mysqlio._to_text(7.0) == "7"


def test_parents_are_created_first():
    fks = [ForeignKey("claims", "customer_id", "customers", "customer_id", 1.0)]
    assert mysqlio._create_order(["claims", "customers"], fks) == ["customers", "claims"]


# ------------------------------------------------------------------ integration (needs a server)

@pytest.fixture(scope="module")
def mysql_settings():
    try:
        settings = mysqlio.load_settings()
    except mysqlio.CredentialsPending as e:
        pytest.skip(str(e))
    try:
        mysqlio.ping(settings)
    except mysqlio.MySQLError as e:
        pytest.skip(f"MySQL server not reachable: {e} (on this machine: start the wampmysqld64 service)")
    return settings


@pytest.fixture(scope="module")
def source_db(mysql_settings, tmp_path_factory):
    from sqlalchemy import text

    from data_gen import load_mysql, make_demo_data

    demo_dir = tmp_path_factory.mktemp("demo")
    make_demo_data.main(["--seed", "8", "--n", "300", "--out", str(demo_dir)])
    names = {"src": f"nazeer_test_src_{secrets.token_hex(3)}", "dst": f"nazeer_test_dst_{secrets.token_hex(3)}",
             "demo": demo_dir}
    load_mysql.load(names["src"], demo_dir, replace=True)
    yield names
    with mysqlio.engine(mysql_settings).begin() as conn:
        for key in ("src", "dst"):
            assert names[key].startswith("nazeer_test_")
            conn.execute(text(f"DROP DATABASE IF EXISTS {mysqlio._q(names[key])}"))


def test_arabic_text_round_trips_unchanged(mysql_settings, source_db):
    from nazeer.tableio import load_csv_folder

    tables, _ = mysqlio.load_mysql(mysql_settings, source_db["src"])
    csv = load_csv_folder(source_db["demo"])
    for t, col in (("claims", "notes"), ("customers", "full_name"), ("customers", "city"), ("customers", "national_id")):
        a = tables[t].sort_values(tables[t].columns[0])[col].tolist()
        b = csv[t].sort_values(csv[t].columns[0])[col].tolist()
        assert a == b, f"{t}.{col} changed in MySQL round trip"


def test_keys_are_read_from_information_schema(mysql_settings, source_db):
    _, schema = mysqlio.load_mysql(mysql_settings, source_db["src"])
    assert schema.primary_keys == {"claims": ["claim_id"], "customers": ["customer_id"]}
    assert [(f.child_table, f.child_column, f.parent_table, f.parent_column) for f in schema.foreign_keys] == \
        [("claims", "customer_id", "customers", "customer_id")]


def test_source_session_is_read_only(mysql_settings, source_db):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with mysqlio.engine(mysql_settings, source_db["src"]).connect() as conn:
        conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
        with pytest.raises(DBAPIError):
            conn.execute(text("DELETE FROM claims WHERE claim_id = -1"))


def test_prod_to_dev_pipeline_and_target_leak_scan(mysql_settings, source_db, tmp_path, monkeypatch):
    from nazeer import pipeline

    monkeypatch.setenv("NAZEER_KEY", "mysql-test-key-0123456789-0123456789")
    code = pipeline.main(["--mysql-db", source_db["src"], "--mysql-target", source_db["dst"], "--mode", "masked",
                          "--apply-fix", "auto", "--out", str(tmp_path)])
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    out = report["mysql_output"]
    assert out["written"] and out["row_counts_match"]
    assert out["leak_scan_of_target"]["verdict"] == "PASS"
    assert code == 0 and report["verdict"] == "PASS"
    landed, schema = mysqlio.load_mysql(mysql_settings, source_db["dst"])
    assert schema.primary_keys == {"claims": ["claim_id"], "customers": ["customer_id"]}
    assert len(schema.foreign_keys) == 1
    twin_csv = pd.read_csv(tmp_path / "twin" / "claims.csv", dtype=str, keep_default_na=False, na_values=[""])
    assert sorted(landed["claims"]["notes"].dropna()) == sorted(twin_csv["notes"].dropna())  # Arabic intact
