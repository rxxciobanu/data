from __future__ import annotations

import logging

import httpx
from py_clob_client.client import ClobClient

from polymarket_orchestrator.config import settings
from polymarket_orchestrator.models import Market, Token

logger = logging.getLogger(__name__)


class PolymarketClient:
    def __init__(self) -> None:
        self.clob = ClobClient(settings.polymarket_host)
        self.gamma_url = settings.gamma_api_host
        self._http = httpx.Client(timeout=30)

    def get_active_markets(self, limit: int | None = None) -> list[Market]:
        """Fetch active, open markets from the Gamma API.

        When *limit* is ``None`` (the default) **all** active markets are
        fetched by paginating through the Gamma API automatically.  Set
        *limit* to a positive integer to cap the number of markets returned.
        """
        fetch_all = limit is None
        page_size = 100  # Gamma API max per request
        if not fetch_all:
            page_size = min(limit, page_size)

        all_raw: list[dict] = []
        offset = 0

        while True:
            want = page_size if fetch_all else min(page_size, limit - len(all_raw))
            if want <= 0:
                break

            resp = self._http.get(
                f"{self.gamma_url}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": want,
                    "offset": offset,
                    "order": "liquidityNum",
                    "ascending": "false",
                },
            )
            resp.raise_for_status()
            page = resp.json()

            if not page:
                break  # No more results

            all_raw.extend(page)
            offset += len(page)
            logger.info("Fetched %d markets so far (page of %d)...", len(all_raw), len(page))

            # If we got fewer than requested, we've reached the end
            if len(page) < want:
                break
            # Safety cap when fetching all — don't loop forever
            if fetch_all and len(all_raw) >= 10_000:
                logger.warning("Safety cap reached at %d markets.", len(all_raw))
                break

        markets: list[Market] = []
        for m in all_raw:
            tokens = self._parse_tokens(m)
            if not tokens:
                continue
            markets.append(
                Market(
                    id=m.get("id", m.get("condition_id", "")),
                    question=m.get("question", ""),
                    description=m.get("description", ""),
                    outcomes=m.get("outcomes", []),
                    tokens=tokens,
                    end_date=m.get("end_date_iso", ""),
                    volume=float(m.get("volume", 0) or 0),
                    liquidity=float(m.get("liquidity", 0) or 0),
                )
            )

        logger.info("Parsed %d markets with valid tokens out of %d total.", len(markets), len(all_raw))

        # Enrich with live CLOB prices
        for market in markets:
            self._enrich_prices(market)

        return markets

    def get_market_odds(self, token_id: str) -> float:
        """Get the midpoint price for a single token from the CLOB."""
        try:
            mid = self.clob.get_midpoint(token_id)
            return float(mid.get("mid", 0) if isinstance(mid, dict) else mid)
        except Exception:
            logger.warning("Failed to get midpoint for token %s", token_id)
            return 0.0

    def get_order_book(self, token_id: str) -> dict:
        """Get the order book for a single token."""
        try:
            return self.clob.get_order_book(token_id)
        except Exception:
            logger.warning("Failed to get order book for token %s", token_id)
            return {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_tokens(self, raw: dict) -> list[Token]:
        """Extract token info from a Gamma API market object."""
        tokens: list[Token] = []

        # Gamma API returns clob_token_ids and outcome_prices as JSON strings
        clob_ids_raw = raw.get("clobTokenIds", raw.get("clob_token_ids", ""))
        outcomes = raw.get("outcomes", [])
        prices_raw = raw.get("outcomePrices", raw.get("outcome_prices", ""))

        # Parse JSON-encoded lists if needed
        if isinstance(clob_ids_raw, str):
            try:
                import json
                clob_ids = json.loads(clob_ids_raw)
            except (ValueError, TypeError):
                return tokens
        else:
            clob_ids = clob_ids_raw

        if isinstance(prices_raw, str):
            try:
                import json
                prices = [float(p) for p in json.loads(prices_raw)]
            except (ValueError, TypeError):
                prices = [0.0] * len(clob_ids)
        else:
            prices = [float(p) for p in prices_raw] if prices_raw else [0.0] * len(clob_ids)

        if isinstance(outcomes, str):
            try:
                import json
                outcomes = json.loads(outcomes)
            except (ValueError, TypeError):
                outcomes = [f"Outcome {i}" for i in range(len(clob_ids))]

        for i, token_id in enumerate(clob_ids):
            outcome = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
            price = prices[i] if i < len(prices) else 0.0
            tokens.append(Token(token_id=str(token_id), outcome=outcome, price=price))

        return tokens

    def _enrich_prices(self, market: Market) -> None:
        """Update token prices with live midpoint from CLOB."""
        for token in market.tokens:
            try:
                price = self.get_market_odds(token.token_id)
                if price > 0:
                    token.price = price
            except Exception:
                pass
