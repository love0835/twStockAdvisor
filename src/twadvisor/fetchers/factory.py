"""Fetcher selection helpers."""

from __future__ import annotations

from twadvisor.fetchers.base import BaseFetcher, FetcherError
from twadvisor.fetchers.finmind import FinMindFetcher
from twadvisor.fetchers.finmind_keys import FinMindKeyRotator
from twadvisor.fetchers.twstock_fetcher import TwstockFetcher
from twadvisor.fetchers.yahoo import YahooFinanceFetcher
from twadvisor.security.keystore import KeyStore
from twadvisor.settings import Settings


def create_fetcher(settings: Settings) -> BaseFetcher:
    """Create the preferred fetcher from settings and available secrets."""

    keystore = KeyStore(settings.security.keyring_service)
    primary = settings.fetcher.primary

    if primary == "finmind":
        try:
            key_rotator = FinMindKeyRotator.from_file(
                settings.fetcher.finmind_keys_path,
                settings.fetcher.finmind_key_state_path,
            )
        except ValueError as exc:
            raise FetcherError(str(exc)) from exc
        if key_rotator is not None:
            return FinMindFetcher(key_rotator=key_rotator)
        token = keystore.get_secret("finmind")
        if token:
            return FinMindFetcher(api_token=token)
    if primary == "twstock":
        return TwstockFetcher()
    if primary == "yahoo":
        return YahooFinanceFetcher()

    for fallback in settings.fetcher.fallback:
        if fallback == "twstock":
            return TwstockFetcher()
        if fallback == "yahoo":
            return YahooFinanceFetcher()

    raise FetcherError("No available fetcher configuration")
