"""Secure storage for the OpenAI API key.

Resolution order: environment variable -> OS credential store (via `keyring`)
-> not configured.

The raw key is never written to any Praxis-managed JSON file (progress.json,
state.json, coaching_prefs.json, etc.) - it only ever lives in the process
environment or the operating system's credential/secret store.
"""

from __future__ import annotations

import os
from typing import Literal

import keyring
import keyring.errors

from praxis.errors import PraxisError

SERVICE_NAME = "praxis"
ENTRY_NAME = "openai_api_key"
ENV_VAR = "PRAXIS_OPENAI_API_KEY"

KeySource = Literal["env", "keyring"]


class CoachingConfigError(PraxisError):
    """The OS credential store could not be used to store/remove the API key."""


def resolve_api_key() -> tuple[str, KeySource] | None:
    """Return `(key, source)` for the first configured key, or `None`."""
    env_key = os.environ.get(ENV_VAR)
    if env_key:
        return env_key, "env"

    try:
        stored = keyring.get_password(SERVICE_NAME, ENTRY_NAME)
    except keyring.errors.KeyringError:
        # No usable backend (e.g. headless Linux with no Secret Service) is
        # treated the same as "not configured" rather than surfacing an error.
        return None
    if stored:
        return stored, "keyring"
    return None


def store_api_key(api_key: str) -> None:
    try:
        keyring.set_password(SERVICE_NAME, ENTRY_NAME, api_key)
    except keyring.errors.KeyringError as exc:
        raise CoachingConfigError(
            "Could not save the API key to the OS credential store. "
            f"Set the {ENV_VAR} environment variable instead."
        ) from exc


def remove_api_key() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, ENTRY_NAME)
    except keyring.errors.PasswordDeleteError:
        # Already absent; removing a non-existent key is a no-op.
        pass
    except keyring.errors.KeyringError as exc:
        raise CoachingConfigError(
            "Could not remove the API key from the OS credential store."
        ) from exc
