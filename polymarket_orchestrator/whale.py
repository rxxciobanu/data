"""Whale wallet tracker — auto-discovers top Polymarket traders and alerts on new trades.

Uses the Polymarket Data API (fully public, no auth):
  - /leaderboard       — discover top profitable traders (30d window)
  - /activity           — per-wallet trade history (BUY/SELL with timestamps)
  - /positions          — current holdings with P&L breakdown
  - /closed-positions   — resolved positions with realizedPnl (for theme expertise)
  - /value              — total portfolio USD value

Theme Expertise System:
  Every market is classified into themes (geopolitics, crypto, elections, etc.)
  by keyword matching on the title.  For each wallet, we compute per-theme
  win rate and P&L from closed (resolved) positions.  When a whale trades
  in their proven domain of expertise, alerts are flagged as high-conviction
  copy signals: "Whale_Alpha (82% win rate on geopolitics, +$45k) just
  bought $20k YES on Iran sanctions market."

State is persisted between runs as a small JSON file so only genuinely
new trades trigger alerts.  First run bootstraps silently (no alert flood).

Graceful degradation: every public method returns empty data on failure.
The debate pipeline is never blocked by whale tracking errors.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"

# ---------------------------------------------------------------------------
# Theme taxonomy — classify markets by keyword matching on title
# ---------------------------------------------------------------------------

# Each theme has a name, a set of keywords (case-insensitive substring match
# on market title), and a minimum number of keyword hits to classify.
# A market can belong to multiple themes.

THEME_KEYWORDS: dict[str, list[str]] = {
    "geopolitics": [
        "iran", "iraq", "russia", "ukraine", "china", "taiwan", "north korea",
        "nato", "sanctions", "war", "invasion", "ceasefire", "missile",
        "military", "troops", "nuclear", "weapons", "conflict", "diplomat",
        "peace talks", "syria", "gaza", "israel", "hamas", "hezbollah",
        "coup", "regime", "territorial", "border", "annex",
    ],
    "us_politics": [
        "trump", "biden", "democrat", "republican", "gop", "congress",
        "senate", "house of representatives", "midterm", "presidential",
        "election", "nominee", "primary", "caucus", "impeach", "speaker",
        "governor", "supreme court", "scotus", "executive order",
        "inauguration", "cabinet", "vice president", "vp", "electoral",
        "swing state", "approval rating", "poll",
    ],
    "crypto": [
        "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain",
        "defi", "nft", "solana", "sol", "xrp", "dogecoin", "altcoin",
        "stablecoin", "usdt", "usdc", "binance", "coinbase", "halving",
        "mining", "token", "memecoin", "web3",
    ],
    "economy": [
        "recession", "inflation", "gdp", "unemployment", "fed ", "fomc",
        "interest rate", "rate cut", "rate hike", "cpi", "jobs report",
        "nonfarm", "debt ceiling", "default", "treasury", "yield",
        "tariff", "trade war", "s&p 500", "s&p500", "nasdaq", "dow jones",
        "stock market", "bear market", "bull market", "ipo",
    ],
    "tech": [
        "ai ", "artificial intelligence", "openai", "chatgpt", "gpt",
        "google", "apple", "meta", "microsoft", "nvidia", "tesla",
        "spacex", "launch", "rocket", "starship", "agi", "llm",
        "semiconductor", "chip", "antitrust", "tiktok",
    ],
    "sports": [
        "nba", "nfl", "mlb", "nhl", "soccer", "football", "basketball",
        "baseball", "tennis", "golf", "olympics", "world cup", "super bowl",
        "championship", "playoffs", "mvp", "premier league", "champions league",
        "ufc", "boxing", "f1", "formula 1", "grand prix",
    ],
    "culture": [
        "oscar", "emmy", "grammy", "box office", "movie", "film",
        "celebrity", "elon musk", "kanye", "taylor swift", "viral",
        "social media", "twitter", "x.com", "tiktok ban",
        "podcast", "streaming", "netflix", "disney",
    ],
    "science_health": [
        "pandemic", "covid", "vaccine", "virus", "outbreak", "who ",
        "fda", "drug", "clinical trial", "disease", "health",
        "climate", "temperature", "carbon", "hurricane", "earthquake",
        "wildfire", "drought", "nasa", "space", "mars", "moon",
    ],
}


def classify_market_themes(title: str) -> list[str]:
    """Classify a market into themes based on title keyword matching.

    Returns a list of theme names (may be empty if no theme matches).
    A market can match multiple themes (e.g. "US sanctions on Iran"
    matches both 'geopolitics' and 'us_politics').
    """
    title_lower = title.lower()
    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in title_lower)
        if hits >= 1:
            themes.append(theme)
    return themes


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class WhaleWallet(BaseModel):
    """A wallet to track — from leaderboard or manual config."""
    address: str
    label: str = ""
    leaderboard_pnl: float = 0.0


class WhaleTrade(BaseModel):
    """A single trade by a tracked wallet."""
    wallet_address: str
    wallet_label: str
    market_slug: str = ""
    market_question: str
    condition_id: str
    outcome: str
    side: str               # "BUY" or "SELL"
    usdc_size: float        # USD value
    price: float            # Price per share (0-1)
    shares: float           # Number of outcome tokens
    timestamp: str          # ISO 8601
    tx_hash: str = ""


class WhalePosition(BaseModel):
    """A current position held by a tracked wallet."""
    wallet_address: str
    wallet_label: str
    condition_id: str
    market_question: str
    outcome: str
    size: float
    avg_price: float
    current_price: float
    initial_value: float
    current_value: float
    pnl: float              # cashPnl
    pnl_pct: float          # percentPnl


class ClosedPosition(BaseModel):
    """A resolved/closed position — used to compute theme expertise."""
    wallet_address: str
    condition_id: str
    market_question: str
    outcome: str
    avg_price: float
    realized_pnl: float         # Dollars gained/lost after resolution
    realized_pnl_pct: float     # Percentage return
    themes: list[str] = Field(default_factory=list)  # Classified themes


class ThemeExpertise(BaseModel):
    """A wallet's track record in a specific theme."""
    theme: str
    wins: int
    losses: int
    total_trades: int
    win_rate: float             # wins / total_trades
    total_pnl: float            # Sum of realizedPnl in this theme
    avg_return_pct: float       # Average percentRealizedPnl
    is_expert: bool = False     # True if win_rate >= 0.60 AND total_trades >= 3


class WalletStats(BaseModel):
    """Performance summary for one wallet."""
    address: str
    label: str
    portfolio_value: float
    total_positions: int
    profitable_positions: int
    win_rate: float
    total_pnl: float
    top_positions: list[WhalePosition] = Field(default_factory=list)
    theme_expertise: list[ThemeExpertise] = Field(default_factory=list)
    strong_themes: list[str] = Field(default_factory=list)  # Themes where is_expert=True


class WhaleAlert(BaseModel):
    """A new trade by a tracked whale, ready for email."""
    trade: WhaleTrade
    wallet_stats: WalletStats | None = None
    overlaps_ai_alert: bool = False
    trade_themes: list[str] = Field(default_factory=list)     # Themes of the market traded
    matching_themes: list[str] = Field(default_factory=list)   # Themes where whale is expert AND trade matches
    is_expert_trade: bool = False  # True if at least one matching expert theme


class WhaleReport(BaseModel):
    """Full output of a whale scan run."""
    wallet_stats: list[WalletStats] = Field(default_factory=list)
    new_trades: list[WhaleTrade] = Field(default_factory=list)
    all_positions: list[WhalePosition] = Field(default_factory=list)
    alerts: list[WhaleAlert] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# State persistence (JSON file — simplest viable approach)
# ---------------------------------------------------------------------------


class WhaleState(BaseModel):
    """Persisted between runs to detect new trades."""
    last_seen: dict[str, str] = Field(default_factory=dict)  # address → ISO timestamp
    last_run: str = ""

    @classmethod
    def load(cls, path: Path) -> WhaleState:
        try:
            if path.exists():
                return cls.model_validate_json(path.read_text())
        except Exception as e:
            logger.warning("Corrupt whale state at %s, starting fresh: %s", path, e)
        return cls()

    def save(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.model_dump_json(indent=2))
        except Exception as e:
            logger.warning("Failed to save whale state to %s: %s", path, e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_wallets(raw: str) -> list[WhaleWallet]:
    """Parse optional extra wallet addresses from JSON string or file path."""
    if not raw.strip():
        return []
    try:
        path = Path(raw)
        if path.exists():
            raw = path.read_text()
        data = json.loads(raw)
        return [WhaleWallet(**w) for w in data]
    except Exception as e:
        logger.warning("Failed to parse WHALE_EXTRA_WALLETS: %s", e)
        return []


def _safe_float(val, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# WhaleTracker
# ---------------------------------------------------------------------------


class WhaleTracker:
    """Discovers and tracks top Polymarket wallets."""

    def __init__(self, settings) -> None:
        self._client = httpx.AsyncClient(timeout=30)
        self._extra_wallets = _parse_wallets(settings.whale_extra_wallets)
        self._leaderboard_count = settings.whale_leaderboard_count
        self._state_path = Path(settings.whale_state_path).expanduser()
        self._state = WhaleState.load(self._state_path)
        self._min_trade_size = settings.whale_min_trade_size

    # ----- HTTP with retry -----

    async def _get(self, path: str, params: dict) -> list | dict:
        """GET from Data API with 3 retries + exponential backoff."""
        for attempt in range(3):
            try:
                resp = await self._client.get(f"{DATA_API}{path}", params=params)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("Whale API rate-limited on %s, retry in %ds", path, wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in (401, 403):
                    logger.error("Whale API auth error %d on %s", resp.status_code, path)
                    return []
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.warning("Whale API %s failed after 3 attempts: %s", path, e)
        return []

    # ----- Leaderboard discovery -----

    async def discover_whales(self) -> list[WhaleWallet]:
        """Auto-discover top profitable traders from the Polymarket leaderboard.

        Merges leaderboard results with any manually configured extra wallets.
        Deduplicates by address.
        """
        wallets: list[WhaleWallet] = list(self._extra_wallets)
        seen = {w.address.lower() for w in wallets}

        raw = await self._get("/leaderboard", {
            "limit": self._leaderboard_count,
            "period": "30d",
        })

        if isinstance(raw, list):
            for entry in raw:
                addr = entry.get("proxyWallet", entry.get("address", ""))
                if not addr or addr.lower() in seen:
                    continue
                label = (
                    entry.get("pseudonym")
                    or entry.get("name")
                    or addr[:10]
                )
                pnl = _safe_float(entry.get("pnl"))
                wallets.append(WhaleWallet(
                    address=addr, label=label, leaderboard_pnl=pnl,
                ))
                seen.add(addr.lower())

        logger.info(
            "Discovered %d whales (%d leaderboard, %d manual).",
            len(wallets), len(wallets) - len(self._extra_wallets),
            len(self._extra_wallets),
        )
        return wallets

    # ----- Data fetching -----

    async def fetch_activity(
        self, address: str, label: str, since: str | None = None,
    ) -> list[WhaleTrade]:
        """Fetch recent TRADE activity for a wallet."""
        params: dict = {
            "user": address,
            "limit": 500,
            "type": "TRADE",
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
        }
        if since:
            try:
                ts = datetime.fromisoformat(since.replace("Z", "+00:00"))
                params["start"] = str(int(ts.timestamp()))
            except ValueError:
                pass

        raw = await self._get("/activity", params)
        if not isinstance(raw, list):
            return []

        trades: list[WhaleTrade] = []
        for entry in raw:
            try:
                trades.append(WhaleTrade(
                    wallet_address=address,
                    wallet_label=label,
                    market_slug=entry.get("slug", ""),
                    market_question=entry.get("title", ""),
                    condition_id=entry.get("conditionId", ""),
                    outcome=entry.get("outcome", ""),
                    side=entry.get("side", ""),
                    usdc_size=_safe_float(entry.get("usdcSize")),
                    price=_safe_float(entry.get("price")),
                    shares=_safe_float(entry.get("size")),
                    timestamp=entry.get("timestamp", ""),
                    tx_hash=entry.get("transactionHash", ""),
                ))
            except Exception as e:
                logger.debug("Skip malformed activity entry: %s", e)

        return trades

    async def fetch_positions(
        self, address: str, label: str,
    ) -> list[WhalePosition]:
        """Fetch current positions for a wallet."""
        raw = await self._get("/positions", {
            "user": address,
            "limit": 500,
            "sizeThreshold": "1",
            "sortBy": "CASHPNL",
            "sortDirection": "DESC",
        })
        if not isinstance(raw, list):
            return []

        positions: list[WhalePosition] = []
        for entry in raw:
            try:
                positions.append(WhalePosition(
                    wallet_address=address,
                    wallet_label=label,
                    condition_id=entry.get("conditionId", ""),
                    market_question=entry.get("title", ""),
                    outcome=entry.get("outcome", ""),
                    size=_safe_float(entry.get("size")),
                    avg_price=_safe_float(entry.get("avgPrice")),
                    current_price=_safe_float(entry.get("curPrice")),
                    initial_value=_safe_float(entry.get("initialValue")),
                    current_value=_safe_float(entry.get("currentValue")),
                    pnl=_safe_float(entry.get("cashPnl")),
                    pnl_pct=_safe_float(entry.get("percentPnl")),
                ))
            except Exception as e:
                logger.debug("Skip malformed position entry: %s", e)

        return positions

    async def fetch_portfolio_value(self, address: str) -> float:
        """Fetch total USD value of a wallet's positions."""
        raw = await self._get("/value", {"user": address})
        if isinstance(raw, dict):
            return _safe_float(raw.get("value"))
        return 0.0

    async def fetch_closed_positions(self, address: str) -> list[ClosedPosition]:
        """Fetch resolved/closed positions for theme expertise analysis.

        Uses /closed-positions which returns positions with realizedPnl
        (actual profit/loss after market resolution).
        """
        all_closed: list[ClosedPosition] = []
        offset = 0
        # Paginate to get full history (critical for accurate theme stats)
        while True:
            raw = await self._get("/closed-positions", {
                "user": address,
                "limit": 500,
                "offset": offset,
            })
            if not isinstance(raw, list) or not raw:
                break

            for entry in raw:
                try:
                    title = entry.get("title", "")
                    all_closed.append(ClosedPosition(
                        wallet_address=address,
                        condition_id=entry.get("conditionId", ""),
                        market_question=title,
                        outcome=entry.get("outcome", ""),
                        avg_price=_safe_float(entry.get("avgPrice")),
                        realized_pnl=_safe_float(entry.get("realizedPnl")),
                        realized_pnl_pct=_safe_float(entry.get("percentRealizedPnl")),
                        themes=classify_market_themes(title),
                    ))
                except Exception as e:
                    logger.debug("Skip malformed closed position: %s", e)

            if len(raw) < 500:
                break  # Last page
            offset += len(raw)

        return all_closed

    # ----- Theme expertise computation -----

    @staticmethod
    def compute_theme_expertise(
        closed_positions: list[ClosedPosition],
    ) -> list[ThemeExpertise]:
        """Compute per-theme win rate and P&L from closed positions.

        A wallet is considered an 'expert' in a theme if:
          - win_rate >= 60% AND
          - at least 3 resolved positions in that theme
        """
        # Accumulate stats per theme
        theme_data: dict[str, dict] = {}
        for pos in closed_positions:
            for theme in pos.themes:
                if theme not in theme_data:
                    theme_data[theme] = {
                        "wins": 0, "losses": 0, "total_pnl": 0.0,
                        "return_pcts": [],
                    }
                td = theme_data[theme]
                if pos.realized_pnl > 0:
                    td["wins"] += 1
                else:
                    td["losses"] += 1
                td["total_pnl"] += pos.realized_pnl
                td["return_pcts"].append(pos.realized_pnl_pct)

        expertise: list[ThemeExpertise] = []
        for theme, td in theme_data.items():
            total = td["wins"] + td["losses"]
            win_rate = td["wins"] / total if total > 0 else 0.0
            avg_ret = (
                sum(td["return_pcts"]) / len(td["return_pcts"])
                if td["return_pcts"] else 0.0
            )
            expertise.append(ThemeExpertise(
                theme=theme,
                wins=td["wins"],
                losses=td["losses"],
                total_trades=total,
                win_rate=win_rate,
                total_pnl=td["total_pnl"],
                avg_return_pct=avg_ret,
                is_expert=(win_rate >= 0.60 and total >= 3),
            ))

        # Sort by PnL descending
        expertise.sort(key=lambda e: e.total_pnl, reverse=True)
        return expertise

    # ----- Stats computation -----

    async def compute_stats(self, wallet: WhaleWallet) -> WalletStats:
        """Build performance stats from positions + portfolio value + theme expertise."""
        positions = await self.fetch_positions(wallet.address, wallet.label)
        value = await self.fetch_portfolio_value(wallet.address)
        closed = await self.fetch_closed_positions(wallet.address)

        profitable = sum(1 for p in positions if p.pnl > 0)
        total_pnl = sum(p.pnl for p in positions)
        win_rate = profitable / len(positions) if positions else 0.0

        # Top 5 by absolute PnL
        top = sorted(positions, key=lambda p: abs(p.pnl), reverse=True)[:5]

        # Theme expertise from closed (resolved) positions
        theme_exp = self.compute_theme_expertise(closed)
        strong = [te.theme for te in theme_exp if te.is_expert]

        if strong:
            logger.info(
                "  %s: expert in %s (%d closed positions analyzed)",
                wallet.label, ", ".join(strong), len(closed),
            )

        return WalletStats(
            address=wallet.address,
            label=wallet.label,
            portfolio_value=value,
            total_positions=len(positions),
            profitable_positions=profitable,
            win_rate=win_rate,
            total_pnl=total_pnl,
            top_positions=top,
            theme_expertise=theme_exp,
            strong_themes=strong,
        )

    # ----- New trade detection -----

    def detect_new_trades(
        self, address: str, trades: list[WhaleTrade],
    ) -> list[WhaleTrade]:
        """Return only trades that occurred after the last-seen timestamp.

        On first run (no last_seen entry), returns [] to bootstrap silently.
        """
        last = self._state.last_seen.get(address)
        if last is None:
            return []  # First run: record timestamps, don't alert
        return [t for t in trades if t.timestamp > last]

    # ----- Main scan -----

    async def scan_wallet(
        self, wallet: WhaleWallet,
    ) -> tuple[WalletStats, list[WhaleTrade]]:
        """Scan a single wallet: compute stats + detect new trades."""
        stats = await self.compute_stats(wallet)

        since = self._state.last_seen.get(wallet.address)
        all_trades = await self.fetch_activity(
            wallet.address, wallet.label, since=since,
        )
        new_trades = self.detect_new_trades(wallet.address, all_trades)

        # Update last-seen to newest trade timestamp
        if all_trades:
            newest = max(t.timestamp for t in all_trades)
            self._state.last_seen[wallet.address] = newest

        return stats, new_trades

    async def scan_all(self) -> WhaleReport:
        """Main entry: discover whales, scan each, build report.

        Wallets are scanned sequentially with a 0.5s courtesy delay
        to avoid hammering the Data API.
        """
        wallets = await self.discover_whales()
        if not wallets:
            logger.info("No whales to track.")
            return WhaleReport()

        all_stats: list[WalletStats] = []
        all_new_trades: list[WhaleTrade] = []
        all_positions: list[WhalePosition] = []

        for wallet in wallets:
            try:
                stats, new_trades = await self.scan_wallet(wallet)
                all_stats.append(stats)
                all_new_trades.extend(new_trades)
                all_positions.extend(stats.top_positions)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(
                    "Whale scan failed for %s (%s): %s",
                    wallet.label, wallet.address[:10], e,
                )

        # Build alerts — only trades above minimum size
        alerts = [
            WhaleAlert(trade=t)
            for t in all_new_trades
            if t.usdc_size >= self._min_trade_size
        ]

        # Attach wallet stats + theme match scoring to alerts
        stats_by_addr = {s.address: s for s in all_stats}
        for alert in alerts:
            alert.wallet_stats = stats_by_addr.get(alert.trade.wallet_address)
            # Classify the market being traded
            alert.trade_themes = classify_market_themes(alert.trade.market_question)
            # Check if whale is an expert in any of the trade's themes
            if alert.wallet_stats and alert.trade_themes:
                expert_themes = set(alert.wallet_stats.strong_themes)
                alert.matching_themes = [
                    t for t in alert.trade_themes if t in expert_themes
                ]
                alert.is_expert_trade = len(alert.matching_themes) > 0

        # Persist state
        self._state.last_run = datetime.now(timezone.utc).isoformat()
        self._state.save(self._state_path)

        total_portfolio = sum(s.portfolio_value for s in all_stats)
        logger.info(
            "Whale scan complete: %d wallets, %d new trades (%d above $%.0f), "
            "$%.0f total portfolio value.",
            len(wallets), len(all_new_trades), len(alerts),
            self._min_trade_size, total_portfolio,
        )

        return WhaleReport(
            wallet_stats=all_stats,
            new_trades=all_new_trades,
            all_positions=all_positions,
            alerts=alerts,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
