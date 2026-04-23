"""Keyring wrapper used by the CLI."""

from __future__ import annotations

import keyring


class KeyStore:
    """Thin wrapper around system keyring."""

    def __init__(self, service_name: str) -> None:
        """Create a keystore bound to a service name."""

        self.service_name = service_name

    def set_secret(self, key: str, value: str) -> None:
        """Store a secret in the system keyring."""

        keyring.set_password(self.service_name, key, value)

    def get_secret(self, key: str) -> str | None:
        """Read a secret from the system keyring."""

        return keyring.get_password(self.service_name, key)
