"""Multi-provider news fetching for AI debate agents.

Fetches recent, relevant news articles and injects them into agent prompts
so prediction market debates are grounded in current events — not just
training data.

Providers:
  1. NewsData.io  — primary, 200 req/day free tier, requires API key
  2. Google News RSS — best-effort fallback, no auth, known flaky

Design hardened by adversarial quant audit (16 issues addressed):
  - Prompt injection defense (sanitization + delimiters)
  - HTML/entity stripping before caching
  - 72-hour date filtering with recency boost
  - asyncio.Lock on shared cache + rate counters
  - Retry with exponential backoff on transient failures
  - Min relevance threshold (no news > garbage news)
  - Provider diversity cap (max 3 per provider in final set)
  - CAPTCHA detection on Google RSS
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import string
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import quote_plus

import httpx
from pydantic import BaseModel

from polymarket_orchestrator.models import Market

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class NewsArticle(BaseModel):
    """A single news article, sanitized and scored."""
    title: str
    source: str
    published_date: str  # ISO 8601 or human-readable
    summary: str         # Sanitized, max ~200 chars
    url: str
    relevance_score: float = 0.0
    provider: str = ""   # "newsdata" or "google_rss"


# ---------------------------------------------------------------------------
# Sanitization (audit fixes #2, #6)
# ---------------------------------------------------------------------------

def _sanitize_html(text: str) -> str:
    """Strip HTML tags and decode entities."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)      # Strip tags
    text = html.unescape(text)                # Decode &amp; etc.
    text = re.sub(r"\s+", " ", text).strip()  # Normalize whitespace
    return text


_INJECTION_PATTERNS = [
    re.compile(r"(?i)^\s*(SYSTEM|IGNORE|OVERRIDE|You are|IMPORTANT|NOTE|INSTRUCTION)"),
    re.compile(r"(?i)(ignore previous|system prompt|override all|disregard above)"),
    re.compile(r"(?i)(set probability|output json|respond with)"),
]


def _sanitize_injection(text: str) -> str:
    """Strip common prompt injection patterns from news text."""
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[FILTERED]", text)
    return text


def _sanitize(text: str) -> str:
    """Full sanitization pipeline: HTML → injection → truncate."""
    text = _sanitize_html(text)
    text = _sanitize_injection(text)
    return text[:500]  # Hard cap on any single field


# ---------------------------------------------------------------------------
# Keyword extraction (audit fix #5)
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    "will the of by a an is are be in on at to for and or not what when how "
    "does do has have can could would should this that these those it its "
    "who whom which where there their was were been being if then than "
    "more most very much many some any all each both few own same such "
    "no nor too also just about between through during before after above "
    "below from up down out off over under again further once "
    "end start starting ending begin beginning hit reach reaches reached "
    "jan feb mar apr may jun jul aug sep oct nov dec "
    "january february march april june july august september october november december "
    "2024 2025 2026 2027 2028 2029 2030".split()
)

# Entity expansion dictionary for prediction market topics
_ENTITY_EXPANSIONS: dict[str, list[str]] = {
    "fed": ["Federal Reserve"],
    "fomc": ["Federal Reserve", "interest rates"],
    "btc": ["Bitcoin", "cryptocurrency"],
    "eth": ["Ethereum", "cryptocurrency"],
    "bitcoin": ["BTC", "cryptocurrency"],
    "ethereum": ["ETH", "cryptocurrency"],
    "gop": ["Republican", "Republicans"],
    "dem": ["Democrat", "Democrats"],
    "dems": ["Democrat", "Democrats"],
    "midterms": ["midterm elections", "Congress"],
    "scotus": ["Supreme Court"],
    "potus": ["President", "White House"],
    "tariff": ["trade", "tariffs", "import duties"],
    "tariffs": ["trade war", "import duties"],
    "gdp": ["economic growth", "economy"],
    "cpi": ["inflation", "consumer prices"],
    "nber": ["recession", "economic contraction"],
    "nato": ["NATO alliance", "military"],
    "opec": ["oil", "petroleum"],
    "sec": ["Securities Exchange Commission"],
    "etf": ["exchange-traded fund"],
    "ipo": ["initial public offering"],
    "ai": ["artificial intelligence"],
    "ev": ["electric vehicle"],
    "uk": ["United Kingdom", "Britain"],
    "eu": ["European Union", "Europe"],
    "china": ["China", "Beijing"],
    "russia": ["Russia", "Moscow"],
    "iran": ["Iran", "Tehran"],
    "israel": ["Israel", "Middle East"],
    "taiwan": ["Taiwan", "cross-strait"],
    "ukraine": ["Ukraine", "Kyiv"],
    "recession": ["economic downturn", "NBER"],
    "inflation": ["CPI", "consumer prices"],
    "election": ["vote", "ballot", "polls"],
    "elections": ["voting", "ballot", "polls"],
    "nominee": ["nomination", "primary", "candidate"],
    "impeach": ["impeachment"],
    "default": ["debt ceiling", "sovereign debt"],
    "shutdown": ["government shutdown", "funding"],
    "pandemic": ["outbreak", "WHO", "virus"],
    "crash": ["market crash", "selloff"],
    "rally": ["market rally", "surge"],
    "ceasefire": ["peace talks", "truce"],
    "sanctions": ["economic sanctions", "embargo"],
    "indictment": ["charges", "prosecution", "trial"],
    "conviction": ["guilty", "verdict", "sentence"],
}

# Financial domain terms for relevance boosting
_FINANCIAL_TERMS = frozenset(
    "price rally crash surge drop fall rise gain loss market trading "
    "stock bond yield rate inflation gdp earnings revenue profit "
    "forecast outlook projection estimate analyst investor fund etf "
    "crypto bitcoin ethereum blockchain defi".split()
)


def extract_keywords(market: Market) -> list[str]:
    """Extract search keywords from a market question and description.

    Strategy:
    1. Tokenize question, strip stopwords and punctuation
    2. Take first sentence of description for context
    3. Expand known entities (Fed → Federal Reserve, etc.)
    4. Filter garbage tokens (short, numeric-only)
    5. Return top 5-8 meaningful terms
    """
    # Tokenize question
    raw = market.question + " "
    # Add first sentence of description
    if market.description:
        first_sentence = market.description.split(".")[0]
        raw += first_sentence

    # Clean and tokenize
    raw = raw.lower()
    raw = raw.translate(str.maketrans("", "", string.punctuation.replace("-", "").replace("$", "")))
    tokens = raw.split()

    # Remove stopwords
    tokens = [t for t in tokens if t not in _STOPWORDS]

    # Entity expansion
    expanded: list[str] = []
    for t in tokens:
        expanded.append(t)
        if t in _ENTITY_EXPANSIONS:
            expanded.extend(_ENTITY_EXPANSIONS[t])

    # Filter: remove tokens < 3 chars, pure numbers, dollar signs
    filtered = []
    seen = set()
    for t in expanded:
        t_clean = t.strip().lower()
        if len(t_clean) < 3:
            continue
        if t_clean.replace(",", "").replace(".", "").isdigit():
            continue
        if t_clean not in seen:
            seen.add(t_clean)
            filtered.append(t)

    # Return top 8 (preserving insertion order = relevance order)
    return filtered[:8]


# ---------------------------------------------------------------------------
# Relevance scoring (audit fixes #3, #8, #15)
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> datetime | None:
    """Best-effort parse of a date string to datetime."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _score_relevance(
    articles: list[NewsArticle],
    keywords: list[str],
    market_question: str,
) -> list[NewsArticle]:
    """Score articles by keyword overlap, recency, and source quality."""
    kw_lower = [k.lower() for k in keywords]
    now = datetime.now(timezone.utc)

    # Check if market is financial (for domain boosting)
    mq_lower = market_question.lower()
    is_financial = any(term in mq_lower for term in _FINANCIAL_TERMS)

    for article in articles:
        title_lower = article.title.lower()
        summary_lower = article.summary.lower()

        # Keyword score: title matches 3x, summary 1x
        kw_score = 0.0
        for kw in kw_lower:
            if kw in title_lower:
                kw_score += 3.0
            if kw in summary_lower:
                kw_score += 1.0

        # Normalize keyword score (max possible = 4 * len(keywords))
        max_kw = 4.0 * max(len(kw_lower), 1)
        kw_score = min(kw_score / max_kw, 1.0)

        # Recency boost: newer articles score higher (audit fix #3)
        recency = 0.5  # Default if date unparseable
        pub_date = _parse_date(article.published_date)
        if pub_date:
            hours_old = (now - pub_date).total_seconds() / 3600
            recency = max(0.0, 1.0 - hours_old / 72.0)

        # Domain boost: financial terms in article boost score for financial markets
        domain_boost = 1.0
        if is_financial:
            combined = title_lower + " " + summary_lower
            financial_hits = sum(1 for t in _FINANCIAL_TERMS if t in combined)
            if financial_hits >= 2:
                domain_boost = 1.3

        # Source quality: NewsData.io articles get quality boost (audit fix #15)
        source_quality = 1.5 if article.provider == "newsdata" else 1.0

        # Combined score
        article.relevance_score = kw_score * recency * domain_boost * source_quality

    return articles


# ---------------------------------------------------------------------------
# Deduplication (audit fix #12)
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> set[str]:
    """Normalize title for dedup comparison."""
    title = title.lower()
    title = title.translate(str.maketrans("", "", string.punctuation))
    words = set(title.split())
    words -= _STOPWORDS
    return words


def _deduplicate_articles(articles: list[NewsArticle]) -> list[NewsArticle]:
    """Remove near-duplicate articles by normalized title similarity.

    Jaccard threshold: 0.35 (after normalization).
    On collision: keep article with higher relevance_score or longer summary.
    """
    if len(articles) <= 1:
        return articles

    kept: list[NewsArticle] = []
    kept_titles: list[set[str]] = []

    for article in articles:
        norm = _normalize_title(article.title)
        if not norm:
            kept.append(article)
            kept_titles.append(norm)
            continue

        is_dup = False
        for i, existing in enumerate(kept_titles):
            if not existing:
                continue
            intersection = norm & existing
            union = norm | existing
            jaccard = len(intersection) / len(union) if union else 0
            if jaccard >= 0.35:
                # Keep the better one
                if len(article.summary) > len(kept[i].summary):
                    kept[i] = article
                    kept_titles[i] = norm
                is_dup = True
                break

        if not is_dup:
            kept.append(article)
            kept_titles.append(norm)

    return kept


# ---------------------------------------------------------------------------
# Per-run cache with asyncio.Lock (audit fixes #4, #11)
# ---------------------------------------------------------------------------

class _RunCache:
    """Per-run in-memory cache. No TTL — lives for entire orchestration run."""

    def __init__(self) -> None:
        self._store: dict[str, list[NewsArticle]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> list[NewsArticle] | None:
        async with self._lock:
            return self._store.get(key)

    async def set(self, key: str, articles: list[NewsArticle]) -> None:
        async with self._lock:
            self._store[key] = articles

    @staticmethod
    def make_key(keywords: list[str]) -> str:
        """Normalized cache key from top significant keywords."""
        significant = sorted(
            [w.lower() for w in keywords if len(w) >= 3 and not w.replace(",", "").isdigit()],
            key=len, reverse=True,
        )[:4]
        return "|".join(sorted(significant))


# ---------------------------------------------------------------------------
# News providers
# ---------------------------------------------------------------------------

class NewsProvider(ABC):
    """Abstract base for news API providers."""

    @abstractmethod
    async def fetch(self, keywords: list[str], max_results: int = 10) -> list[NewsArticle]:
        """Fetch news matching keywords. NEVER raises — returns [] on failure."""
        ...


class NewsDataProvider(NewsProvider):
    """NewsData.io — 200 req/day free tier, excellent coverage."""

    BASE_URL = "https://newsdata.io/api/1/latest"

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._client = client
        self._requests_today = 0
        self._daily_limit = 190  # Leave 10 buffer
        self._lock = asyncio.Lock()

    async def fetch(self, keywords: list[str], max_results: int = 10) -> list[NewsArticle]:
        async with self._lock:
            if self._requests_today >= self._daily_limit:
                logger.debug("NewsData.io daily budget exhausted (%d/%d).",
                             self._requests_today, self._daily_limit)
                return []
            self._requests_today += 1

        query = " OR ".join(keywords[:5])
        params = {
            "apikey": self._api_key,
            "q": query,
            "language": "en",
            "size": min(max_results, 10),
            "timeframe": 72,  # Last 72 hours (audit fix #3)
        }

        # Retry with exponential backoff (audit fix #7)
        for attempt in range(3):
            try:
                resp = await self._client.get(self.BASE_URL, params=params, timeout=10)
                if resp.status_code == 429:
                    wait = min(2 ** attempt, 8)
                    logger.warning("NewsData.io 429 — retrying in %ds (attempt %d/3)", wait, attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in (401, 403):
                    logger.error("NewsData.io auth error (%d). Check API key.", resp.status_code)
                    return []
                resp.raise_for_status()
                break
            except httpx.HTTPStatusError:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.warning("NewsData.io failed after 3 attempts.")
                return []
            except Exception as e:
                logger.warning("NewsData.io request error: %s", e)
                return []
        else:
            return []

        try:
            data = resp.json()
            results = data.get("results") or []
        except Exception:
            logger.warning("NewsData.io: invalid JSON response.")
            return []

        articles: list[NewsArticle] = []
        for item in results[:max_results]:
            articles.append(NewsArticle(
                title=_sanitize(item.get("title", "")),
                source=_sanitize(item.get("source_name", item.get("source_id", "Unknown"))),
                published_date=item.get("pubDate", ""),
                summary=_sanitize(item.get("description", ""))[:200],
                url=item.get("link", ""),
                provider="newsdata",
            ))

        return articles


class GoogleNewsRSSProvider(NewsProvider):
    """Google News RSS — free, no auth, but known to be flaky.

    Health checks: CAPTCHA detection, bozo flag, empty result validation.
    """

    BASE_URL = "https://news.google.com/rss/search"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch(self, keywords: list[str], max_results: int = 10) -> list[NewsArticle]:
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser not installed. Google News RSS unavailable.")
            return []

        query = quote_plus(" ".join(keywords[:5]) + " when:3d")
        url = f"{self.BASE_URL}?q={query}&hl=en-US&gl=US&ceid=US:en"

        try:
            resp = await self._client.get(url, timeout=10)
            body = resp.text

            # CAPTCHA detection (audit fix #1)
            if "<form" in body.lower() and "captcha" in body.lower():
                logger.warning("Google News RSS returned CAPTCHA. Provider degraded.")
                return []
            if resp.status_code != 200:
                logger.warning("Google News RSS HTTP %d.", resp.status_code)
                return []

        except Exception as e:
            logger.warning("Google News RSS request failed: %s", e)
            return []

        # feedparser is sync — run off the event loop
        try:
            feed = await asyncio.to_thread(feedparser.parse, body)
        except Exception as e:
            logger.warning("feedparser error: %s", e)
            return []

        # Health checks (audit fix #13)
        if getattr(feed, "bozo", False) and not feed.entries:
            logger.warning("Google News RSS: bozo feed with no entries.")
            return []

        if not feed.entries:
            logger.debug("Google News RSS: 0 entries for query '%s'.", " ".join(keywords[:5]))
            return []

        articles: list[NewsArticle] = []
        for entry in feed.entries[:max_results]:
            title = _sanitize(entry.get("title", ""))
            # Google News titles often end with " - Source Name"
            source = "Google News"
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0].strip()
                source = parts[1].strip()

            published = entry.get("published", entry.get("updated", ""))

            summary = _sanitize(entry.get("summary", entry.get("description", "")))[:200]

            articles.append(NewsArticle(
                title=title,
                source=source,
                published_date=published,
                summary=summary,
                url=entry.get("link", ""),
                provider="google_rss",
            ))

        logger.debug("Google News RSS: %d articles for '%s'.", len(articles), " ".join(keywords[:3]))
        return articles


# ---------------------------------------------------------------------------
# News aggregator (main public interface)
# ---------------------------------------------------------------------------

class NewsAggregator:
    """Multi-provider news fetcher with caching, dedup, and relevance filtering.

    Usage:
        aggregator = NewsAggregator(settings)
        articles = await aggregator.get_news_for_market(market)
        ...
        await aggregator.close()
    """

    def __init__(self, config) -> None:
        self._client = httpx.AsyncClient(timeout=15)
        self._cache = _RunCache()
        self._max_articles = getattr(config, "news_max_articles", 5)
        self._min_relevance = 0.10  # Below this → don't inject (audit fix #8)

        # Build provider chain
        self._providers: list[NewsProvider] = []
        api_key = getattr(config, "newsdata_api_key", "")
        if api_key:
            self._providers.append(NewsDataProvider(api_key, self._client))
            logger.info("NewsData.io provider enabled.")
        self._providers.append(GoogleNewsRSSProvider(self._client))
        logger.info("News aggregator initialized with %d provider(s).", len(self._providers))

    async def get_news_for_market(self, market: Market) -> list[NewsArticle]:
        """Fetch relevant news for a market. Returns [] on total failure."""
        keywords = extract_keywords(market)
        if not keywords:
            logger.debug("No keywords extracted for '%s'.", market.question[:40])
            return []

        # Check cache
        cache_key = _RunCache.make_key(keywords)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache HIT for '%s' (key=%s).", market.question[:40], cache_key)
            return cached

        # Query all providers in parallel
        raw_results = await asyncio.gather(
            *[p.fetch(keywords, max_results=self._max_articles * 2) for p in self._providers],
            return_exceptions=True,
        )

        # Merge successful results
        all_articles: list[NewsArticle] = []
        for i, result in enumerate(raw_results):
            pname = self._providers[i].__class__.__name__
            if isinstance(result, list):
                if result:
                    logger.info("Provider %s: %d articles.", pname, len(result))
                all_articles.extend(result)
            else:
                logger.warning("Provider %s failed: %s", pname, result)

        if not all_articles:
            logger.debug("No news found for '%s'.", market.question[:40])
            await self._cache.set(cache_key, [])
            return []

        # Pipeline: dedupe → score → filter → sort → provider diversity → truncate
        articles = _deduplicate_articles(all_articles)
        articles = _score_relevance(articles, keywords, market.question)
        articles = [a for a in articles if a.relevance_score >= self._min_relevance]
        articles.sort(key=lambda a: a.relevance_score, reverse=True)

        # Provider diversity: max 3 from any single provider (audit fix #15)
        final: list[NewsArticle] = []
        provider_counts: dict[str, int] = {}
        for a in articles:
            count = provider_counts.get(a.provider, 0)
            if count < 3:
                final.append(a)
                provider_counts[a.provider] = count + 1
            if len(final) >= self._max_articles:
                break

        logger.info(
            "News for '%s': %d raw → %d deduped → %d relevant → %d final.",
            market.question[:40], len(all_articles), len(articles),
            sum(1 for a in articles), len(final),
        )

        await self._cache.set(cache_key, final)
        return final

    async def get_news_for_batch(
        self,
        markets: list[Market],
    ) -> dict[str, list[NewsArticle]]:
        """Pre-fetch news for a batch of markets concurrently."""
        tasks = {m.id: self.get_news_for_market(m) for m in markets}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        return {
            mid: (arts if isinstance(arts, list) else [])
            for mid, arts in zip(tasks.keys(), results)
        }

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
