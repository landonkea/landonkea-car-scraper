# ───────────────────────────────────────────────────────────────────
# Price comparison against market average
# ───────────────────────────────────────────────────────────────────
# Since KBB doesn't have a free API, we use our own scraped data
# to calculate market average for each make/model/year and flag
# deals priced significantly below that average.
# ───────────────────────────────────────────────────────────────────

from typing import Optional
from statistics import mean, stdev

# Thresholds for deal ratings
EXCEPTIONAL_DISCOUNT_PCT = 15  # 15%+ below average = exceptional
GOOD_DISCOUNT_PCT = 10         # 10%+ below average = good deal


def compare_to_market(
    listing_price: float,
    make: str,
    model: str,
    year: int,
    all_prices: list[float],
) -> dict:
    """
    Compare a listing price to the market average for that make/model/year.
    Uses all_prices (prices of same make/model from scraped data).
    Returns dict with avg_price, discount_pct, and rating.
    """
    if not all_prices or len(all_prices) < 3:
        return {
            "avg_price": None,
            "discount_pct": None,
            "rating": "unknown",
        }

    avg_price = mean(all_prices)
    if avg_price <= 0:
        return {
            "avg_price": None,
            "discount_pct": None,
            "rating": "unknown",
        }

    discount_pct = ((avg_price - listing_price) / avg_price) * 100

    if discount_pct >= EXCEPTIONAL_DISCOUNT_PCT:
        rating = "exceptional"
    elif discount_pct >= GOOD_DISCOUNT_PCT:
        rating = "good"
    elif discount_pct > 0:
        rating = "fair"
    else:
        rating = "above_market"

    return {
        "avg_price": round(avg_price),
        "discount_pct": round(discount_pct, 1),
        "rating": rating,
    }


def get_market_prices(
    make: str,
    model: str,
    all_listings: list,
) -> list[float]:
    """
    Get all prices for the same make/model from a list of ScrapedListing objects.
    """
    return [
        l.price_usd
        for l in all_listings
        if l.make and l.make.lower() == make.lower()
        and l.model and l.model.lower() == model.lower()
        and l.price_usd > 0
    ]
