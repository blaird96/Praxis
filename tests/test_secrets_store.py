"""Tests for OpenAI API key resolution/storage (env var + OS credential store)."""

from __future__ import annotations

import keyring.errors
import pytest

from praxis.coaching import secrets_store as store


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(store.ENV_VAR, raising=False)


class _FakeKeyring:
    """In-memory stand-in for the `keyring` module's password functions."""

    def __init__(self) -> None:
        self._passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._passwords:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._passwords[key]


class _BrokenKeyring:
    """Simulates an environment with no usable keyring backend."""

    def get_password(self, service: str, username: str) -> str | None:
        raise keyring.errors.KeyringError("no backend available")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise keyring.errors.KeyringError("no backend available")

    def delete_password(self, service: str, username: str) -> None:
        raise keyring.errors.KeyringError("no backend available")


def test_resolve_returns_none_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeKeyring()
    monkeypatch.setattr(store.keyring, "get_password", fake.get_password)
    assert store.resolve_api_key() is None


def test_env_var_takes_precedence_over_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeKeyring()
    fake.set_password(store.SERVICE_NAME, store.ENTRY_NAME, "stored-key")
    monkeypatch.setattr(store.keyring, "get_password", fake.get_password)
    monkeypatch.setenv(store.ENV_VAR, "env-key")

    result = store.resolve_api_key()
    assert result == ("env-key", "env")


def test_store_then_resolve_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeKeyring()
    monkeypatch.setattr(store.keyring, "get_password", fake.get_password)
    monkeypatch.setattr(store.keyring, "set_password", fake.set_password)

    store.store_api_key("sk-test-123")
    assert store.resolve_api_key() == ("sk-test-123", "keyring")


def test_remove_deletes_stored_key(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeKeyring()
    fake.set_password(store.SERVICE_NAME, store.ENTRY_NAME, "sk-test-123")
    monkeypatch.setattr(store.keyring, "get_password", fake.get_password)
    monkeypatch.setattr(store.keyring, "delete_password", fake.delete_password)

    store.remove_api_key()
    assert fake.get_password(store.SERVICE_NAME, store.ENTRY_NAME) is None


def test_remove_is_a_no_op_when_nothing_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeKeyring()
    monkeypatch.setattr(store.keyring, "delete_password", fake.delete_password)
    store.remove_api_key()  # should not raise


def test_resolve_treats_keyring_error_as_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _BrokenKeyring()
    monkeypatch.setattr(store.keyring, "get_password", broken.get_password)
    assert store.resolve_api_key() is None


def test_store_raises_coaching_config_error_when_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _BrokenKeyring()
    monkeypatch.setattr(store.keyring, "set_password", broken.set_password)
    with pytest.raises(store.CoachingConfigError):
        store.store_api_key("sk-test-123")


def test_remove_raises_coaching_config_error_when_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _BrokenKeyring()
    monkeypatch.setattr(store.keyring, "delete_password", broken.delete_password)
    with pytest.raises(store.CoachingConfigError):
        store.remove_api_key()
