"""Discord webhook notifier."""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from twadvisor.models import Action, Recommendation
from twadvisor.notifier.base import BaseNotifier


class DiscordWebhookNotifier(BaseNotifier):
    """Send recommendation embeds to a Discord webhook."""

    def __init__(
        self,
        webhook_url: str,
        mention_user_id: str = "",
        color_map: dict[str, int] | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Create a Discord notifier."""

        self.webhook_url = webhook_url
        self.mention_user_id = mention_user_id
        self.color_map = color_map or {
            Action.BUY.value: 0x2ECC71,
            Action.SELL.value: 0xE74C3C,
            Action.HOLD.value: 0x95A5A6,
            Action.WATCH.value: 0x95A5A6,
        }
        self.timeout = timeout

    async def notify(self, recs: list[Recommendation], market_view: str) -> None:
        """Send Discord embeds in chunks of up to 10."""

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for start in range(0, len(recs), 10):
                chunk = recs[start : start + 10]
                payload = {
                    "content": f"<@{self.mention_user_id}> New recommendations" if self.mention_user_id else None,
                    "username": "TwStockAdvisor",
                    "embeds": [self._to_embed(rec, market_view) for rec in chunk],
                }
                response = await client.post(self.webhook_url, json=payload)
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", "1"))
                    await asyncio.sleep(retry_after)
                    response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()

    def _to_embed(self, rec: Recommendation, market_view: str) -> dict:
        """Convert a recommendation into a Discord embed payload."""

        title_map = {
            Action.BUY.value: "Buy",
            Action.SELL.value: "Sell",
            Action.HOLD.value: "Hold",
            Action.WATCH.value: "Watch",
        }
        return {
            "title": f"{title_map[rec.action.value]} {rec.symbol}",
            "description": market_view[:200],
            "color": self.color_map[rec.action.value],
            "fields": [
                {"name": "Action", "value": rec.action.value, "inline": True},
                {"name": "Qty", "value": str(rec.qty), "inline": True},
                {"name": "Price", "value": "-" if rec.price is None else str(rec.price), "inline": True},
                {
                    "name": "Stop / Target",
                    "value": f"{rec.stop_loss or '-'} / {rec.take_profit or '-'}",
                    "inline": False,
                },
                {"name": "Reason", "value": rec.reason[:1024], "inline": False},
            ],
            "footer": {"text": f"strategy={rec.strategy.value} {datetime.now().isoformat(sep=' ', timespec='seconds')}"},
        }
