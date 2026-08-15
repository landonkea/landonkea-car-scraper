# ───────────────────────────────────────────────────────────────────
# KBB price comparison, flags deals below market value
# ───────────────────────────────────────────────────────────────────
# Uses Kelley Blue Book's public API to compare listing prices
# against estimated market value. Deals priced significantly below
# KBB are flagged as exceptional.
# ───────────────────────────────────────────────────────────────────

from typing import Optional
from functools import lru_cache

import requests


KBB_API = "https://www.kbb.com/wp-json/kbb/v2/price Advisor"

# How far below KBB to consider a deal "exceptional"
EXCEPTIONAL_DISCOUNT_PCT = 15  # 15%+ below KBB
GOOD_DISCOUNT_PCT = 10         # 10%+ below KBB


def get_kbb_price(
    year: int,
    make: str,
    model: str,
    mileage: int,
    condition: str = "Good",
    zip_code: str = "85001",
) -> Optional[float]:
    """
    Estimate KBB price for a vehicle.
    Returns None if unavailable.
    """
    # This is a placeholder - KBB doesn't have a free public API
    # In production, you'd need either:
    # 1. A paid KBB API key
    # 2. Web scraping (against ToS)
    # 3. A third-party service

    # For now, return None to skip KBB comparison
    return None


def compare_to_kbb(
    listing_price: float,
    year: int,
    make: str,
    model: str,
    mileage: int,
    zip_code: str = "85001",
) -> dict:
    """
    Compare a listing price to KBB estimated value.
    Returns dict with kbb_price, discount_pct, and rating.
    """
    kbb_price = get_kbb_price(year, make, model, mileage, zip_code=zip_code)

    if not kbb_price or kbb_price <= 0:
        return {
            "kbb_price": None,
            "discount_pct": None,
            "rating": "unknown",
        }

    discount_pct = ((kbb_price - listing_price) / kbb_price) * 100

    if discount_pct >= EXCEPTIONAL_DISCOUNT_PCT:
        rating = "exceptional"
    elif discount_pct >= GOOD_DISCOUNT_PCT:
        rating = "good"
    elif discount_pct > 0:
        rating = "fair"
    else:
        rating = "above_market"

    return {
        "kbb_price": kbb_price,
        "discount_pct": round(discount_pct, 1),
        "rating": rating,
    }
