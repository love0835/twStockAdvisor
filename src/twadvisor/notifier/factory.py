"""Notifier selection helpers."""

from __future__ import annotations

from twadvisor.notifier.base import BaseNotifier
from twadvisor.notifier.console import ConsoleNotifier
from twadvisor.notifier.discord import DiscordWebhookNotifier
from twadvisor.security.keystore import KeyStore
from twadvisor.settings import Settings


class FanoutNotifier(BaseNotifier):
    """Dispatch notifications to multiple channels."""

    def __init__(self, notifiers: list[BaseNotifier]) -> None:
        """Create a fanout notifier."""

        self.notifiers = notifiers

    async def notify(self, recs, market_view: str) -> None:
        """Send notifications to every configured notifier."""

        for notifier in self.notifiers:
            try:
                await notifier.notify(recs, market_view)
            except Exception:
                continue


def create_notifier(settings: Settings) -> BaseNotifier:
    """Create the configured notification fanout."""

    notifiers: list[BaseNotifier] = []
    if "console" in settings.notifier.channels:
        notifiers.append(ConsoleNotifier())
    if "discord" in settings.notifier.channels:
        secret_name = settings.notifier.discord.webhook_url_key
        webhook_url = KeyStore(settings.security.keyring_service).get_secret(secret_name)
        if webhook_url:
            notifiers.append(
                DiscordWebhookNotifier(
                    webhook_url=webhook_url,
                    mention_user_id=settings.notifier.discord.mention_user_id,
                    color_map={
                        "buy": settings.notifier.discord.embed_color_buy,
                        "sell": settings.notifier.discord.embed_color_sell,
                        "hold": settings.notifier.discord.embed_color_hold,
                        "watch": settings.notifier.discord.embed_color_hold,
                    },
                )
            )
    return FanoutNotifier(notifiers or [ConsoleNotifier()])
