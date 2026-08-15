# ───────────────────────────────────────────────────────────────────
# Daily price-stat tracker, feeds the trend charts
# ───────────────────────────────────────────────────────────────────
# Rolls up listings into per-model min/avg/max rows per day.
# Charts read this table to plot price trends over time.
# ───────────────────────────────────────────────────────────────────

import statistics
from datetime import datetime, timezone

from config import SearchConfig
from database import DailyPriceStat, Listing


def _group_key_for_listing(listing: Listing, search: SearchConfig) -> str | None:
    """
    Figure out which group a listing belongs to.

    For car searches, groups by make (e.g. "Honda", "Chevy").
    """
    if listing.make:
        return listing.make
    return None


def record_daily_stats(db, search: SearchConfig, listings: list[Listing]) -> int:
    """
    Roll up today's listings into per-model min/avg/max rows.

    Returns the number of rows written/updated.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    by_group: dict[str, list[float]] = {}
    for listing in listings:
        key = _group_key_for_listing(listing, search)
        if key is None:
            continue
        by_group.setdefault(key, []).append(listing.price_usd)

    written = 0
    for group_key, prices in by_group.items():
        if not prices:
            continue
        row = (
            db.query(DailyPriceStat)
            .filter(DailyPriceStat.date == today, DailyPriceStat.group_key == group_key)
            .first()
        )
        if row is None:
            row = DailyPriceStat(date=today, product_name=search.product_name, group_key=group_key)
            db.add(row)
        row.product_name = search.product_name
        row.min_price = min(prices)
        row.avg_price = round(statistics.mean(prices), 2)
        row.max_price = max(prices)
        row.listing_count = len(prices)
        written += 1

    db.commit()
    return written
