import os

import pytest

from nazeer.config import KEY_ENV, MIN_KEY_LEN, OFFLINE_ENV, KeyConfigError, load_key


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    with pytest.raises(KeyConfigError):
        load_key()


def test_short_key_raises_without_echoing_it(monkeypatch):
    monkeypatch.setenv(KEY_ENV, "short-secret")
    with pytest.raises(KeyConfigError) as exc:
        load_key()
    assert "short-secret" not in str(exc.value)


def test_valid_key_returns_bytes(monkeypatch):
    key = "k" * MIN_KEY_LEN
    monkeypatch.setenv(KEY_ENV, key)
    assert load_key() == key.encode("utf-8")


def test_package_import_forces_offline():
    import nazeer  # noqa: F401

    for name, value in OFFLINE_ENV.items():
        assert os.environ.get(name) == value
