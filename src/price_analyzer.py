# ───────────────────────────────────────────────────────────────────
# Price analyzer, computes deal scores and picks top deals
# ───────────────────────────────────────────────────────────────────
# Every scraped listing gets a deal score from 0 (bad) to 100
# (amazing). Based on: price vs median, mileage, year, condition,
# source reliability, and car-specific bonuses.
# ───────────────────────────────────────────────────────────────────

import statistics
from typing import Optional

from database import Listing
from config import Config
from product_types import PRODUCT_TYPES


SUSPICIOUS_PRICE_RATIO = 0.5
SUSPICIOUS_MIN_SAMPLE = 3
SUSPICIOUS_CONDITION_KEYWORDS = ["new", "sealed", "brand new", "factory sealed"]
SUSPICIOUS_TAG = "VERIFY PRICE, "

DEFAULT_SOURCE_RELIABILITY_BONUS: dict[str, float] = {
    "craigslist": -3,
    "offerup": -3,
    "facebook": -1,
    "ebay": 0,
    "cargurus": 1,
    "autotrader": 1,
}


def is_meaningful_price_drop(old_price: Optional[float], new_price: float,
                              config: Config) -> bool:
    """Decide if a price change is worth alerting on."""
    drop_cfg = config.price_drop
    if not drop_cfg.enabled:
        return False
    if old_price is None:
        return False
    if old_price <= 0 or new_price >= old_price:
        return False
    drop_usd = old_price - new_price
    drop_percent = (drop_usd / old_price) * 100
    return drop_usd >= drop_cfg.min_drop_usd and drop_percent >= drop_cfg.min_drop_percent


_BREAKDOWN_LABELS: dict[str, str] = {
    "base": "base",
    "price_vs_median": "price",
    "condition": "condition",
    "source_reliability": "source",
    "spec_bonus": "specs",
    "clamp_adjustment": "clamp",
    "suspicious_price_cap": "cap",
    "no_batch_data_baseline": "baseline",
}
_BREAKDOWN_ABSOLUTE_KEYS = {"base", "no_batch_data_baseline"}


def format_score_breakdown(breakdown: Optional[dict]) -> str:
    """Render a deal-score breakdown dict as a compact string."""
    if not breakdown:
        return ""
    parts = []
    for key, value in breakdown.items():
        label = _BREAKDOWN_LABELS.get(key, key)
        if key in _BREAKDOWN_ABSOLUTE_KEYS:
            parts.append(f"{label} {value:.0f}")
        else:
            value = value + 0.0
            sign = "+" if value >= 0 else ""
            parts.append(f"{label} {sign}{value:.1f}")
    return " | ".join(parts)


class PriceAnalyzer:
    """Analyzes listing prices and computes deal scores."""

    def __init__(self, config: Config):
        self.config = config
        self.listings: list[Listing] = []
        self._stats: Optional[dict] = None

    def add_listings(self, listings: list[Listing]):
        self.listings.extend(listings)
        self._stats = None

    def _compute_stats(self) -> dict:
        if not self.listings:
            return {"count": 0, "mean": 0, "median": 0, "min": 0, "max": 0, "std_dev": 0, "q25": 0, "q75": 0}
        prices = [l.price_usd for l in self.listings]
        prices_sorted = sorted(prices)
        n = len(prices_sorted)
        mean_val = statistics.mean(prices)
        median_val = statistics.median(prices)
        q25 = prices_sorted[n // 4] if n >= 4 else prices_sorted[0]
        q75 = prices_sorted[3 * n // 4] if n >= 4 else prices_sorted[-1]
        try:
            std_dev = statistics.stdev(prices) if n > 1 else 0
        except statistics.StatisticsError:
            std_dev = 0
        self._stats = {
            "count": n, "mean": round(mean_val, 2), "median": round(median_val, 2),
            "min": min(prices), "max": max(prices), "std_dev": round(std_dev, 2),
            "q25": q25, "q75": q75,
        }
        return self._stats

    def _is_suspiciously_cheap(self, listing: Listing, stats: dict) -> bool:
        min_sample = getattr(self.config.price, "suspicious_min_sample", SUSPICIOUS_MIN_SAMPLE)
        price_ratio = getattr(self.config.price, "suspicious_price_ratio", SUSPICIOUS_PRICE_RATIO)
        median = stats.get("median", 0)
        if median <= 0 or stats.get("count", 0) < min_sample:
            return False
        if listing.price_usd >= median * price_ratio:
            return False
        text = f"{listing.condition or ''} {listing.title or ''}".lower()
        return any(kw in text for kw in SUSPICIOUS_CONDITION_KEYWORDS)

    def _threshold_key(self, listing: Listing):
        """Key for looking up great_deal_usd/good_deal_usd thresholds."""
        return self.config.search.product_type

    def _source_reliability_bonus(self, source: str) -> float:
        config_overrides = getattr(self.config.price, "source_reliability", None) or {}
        if source in config_overrides:
            return float(config_overrides[source])
        return float(DEFAULT_SOURCE_RELIABILITY_BONUS.get(source, 0.0))

    def _score_listing(self, listing: Listing) -> float:
        """Compute a deal score for one listing (0-100)."""
        stats = self._compute_stats()
        if stats["count"] == 0:
            key = self._threshold_key(listing)
            great = self.config.price.great_deal_usd.get(key, 5000)
            good = self.config.price.good_deal_usd.get(key, 5500)
            if listing.price_usd <= great:
                score = 90.0
            elif listing.price_usd <= good:
                score = 70.0
            else:
                score = 40.0
            listing.deal_score_breakdown = {"no_batch_data_baseline": score}
            return score

        breakdown: dict[str, float] = {"base": 50.0}
        score = 50.0

        median = stats["median"]
        price_component = 0.0
        if median > 0:
            if listing.price_usd < median:
                ratio = (median - listing.price_usd) / median
                price_component = min(ratio * 100, 30)
            else:
                ratio = (listing.price_usd - median) / median
                price_component = -min(ratio * 50, 20)
        score += price_component
        breakdown["price_vs_median"] = round(price_component, 1)

        condition_component = 0.0
        if listing.condition:
            cond_lower = listing.condition.lower()
            if any(w in cond_lower for w in ["new", "certified", "excellent"]):
                condition_component = 5
            elif "open" in cond_lower:
                condition_component = 3
            elif "good" in cond_lower:
                condition_component = 1
        score += condition_component
        breakdown["condition"] = condition_component

        source_component = self._source_reliability_bonus(listing.source)
        score += source_component
        breakdown["source_reliability"] = source_component

        s = self.config.search
        handler = PRODUCT_TYPES[s.product_type]
        spec_component = handler.score_bonuses(listing, s)
        score += spec_component
        breakdown["spec_bonus"] = round(spec_component, 1)

        pre_clamp_score = score
        score = max(0, min(100, score))
        if score != pre_clamp_score:
            breakdown["clamp_adjustment"] = round(score - pre_clamp_score, 1)

        if self._is_suspiciously_cheap(listing, stats):
            capped_score = min(score, 10.0)
            if capped_score != score:
                breakdown["suspicious_price_cap"] = round(capped_score - score, 1)
            score = capped_score

        listing.deal_score_breakdown = breakdown
        return round(score, 1)

    def analyze(self, listings: Optional[list[Listing]] = None) -> list[Listing]:
        """Analyze listings and attach deal scores."""
        if listings is not None:
            self.add_listings(listings)
        for listing in self.listings:
            listing.deal_score = self._score_listing(listing)
            key = self._threshold_key(listing)
            threshold = self.config.price.great_deal_usd.get(key, 5000)
            listing.is_great_deal = listing.price_usd <= threshold
            if self._is_suspiciously_cheap(listing, self._compute_stats()):
                listing.is_great_deal = False
                if not listing.title.startswith(SUSPICIOUS_TAG):
                    listing.title = SUSPICIOUS_TAG + listing.title
        self.listings.sort(key=lambda l: l.deal_score or 0, reverse=True)
        return self.listings

    def get_top_deals(self, count: Optional[int] = None) -> list[Listing]:
        if count is None:
            count = self.config.price.top_deals_count
        return self.listings[:count]

    def get_stats(self) -> dict:
        return self._compute_stats()
