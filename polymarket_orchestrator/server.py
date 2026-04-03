"""FastMCP server exposing Polymarket data as tools for external AI agents."""
from __future__ import annotations

import json

from fastmcp import FastMCP

from polymarket_orchestrator.polymarket import PolymarketClient

mcp = FastMCP("Polymarket")

_client: PolymarketClient | None = None


def _get_client() -> PolymarketClient:
    global _client
    if _client is None:
        _client = PolymarketClient()
    return _client


@mcp.tool
def get_active_markets(limit: int | None = None) -> str:
    """Fetch active prediction markets from Polymarket, sorted by liquidity.

    Args:
        limit: Maximum number of markets to return.  Pass None (default) to
            fetch ALL active markets via automatic pagination.

    Returns:
        JSON list of markets with question, outcomes, prices, volume, and liquidity.
    """
    client = _get_client()
    markets = client.get_active_markets(limit=limit)
    return json.dumps([m.model_dump() for m in markets], indent=2)


@mcp.tool
def get_market_odds(token_id: str) -> str:
    """Get the current midpoint price/odds for a specific outcome token.

    Args:
        token_id: The CLOB token ID for the outcome.

    Returns:
        JSON with the token_id and its current midpoint price (0.0-1.0).
    """
    client = _get_client()
    price = client.get_market_odds(token_id)
    return json.dumps({"token_id": token_id, "midpoint_price": price})


@mcp.tool
def get_order_book(token_id: str) -> str:
    """Get the full order book for a specific outcome token.

    Args:
        token_id: The CLOB token ID for the outcome.

    Returns:
        JSON order book with bids and asks.
    """
    client = _get_client()
    book = client.get_order_book(token_id)
    return json.dumps(book, default=str)


if __name__ == "__main__":
    mcp.run()
