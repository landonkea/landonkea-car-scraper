# ───────────────────────────────────────────────────────────────────
# GitHub Pages data generator
# ───────────────────────────────────────────────────────────────────
# Exports daily_price_stats to docs/data/daily_stats.json for
# the GitHub Pages trend charts.
# ───────────────────────────────────────────────────────────────────

import json
import os

from database import DailyPriceStat


def generate_pages_data(db, output_path: str = "docs/data/daily_stats.json") -> int:
    """Export all daily price stats to a JSON file."""
    rows = db.query(DailyPriceStat).order_by(DailyPriceStat.date.asc()).all()
    data: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        product_group = data.setdefault(row.product_name, {})
        series = product_group.setdefault(row.group_key, [])
        series.append({
            "date": row.date,
            "min": row.min_price,
            "avg": row.avg_price,
            "max": row.max_price,
            "count": row.listing_count,
        })
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    return len(rows)
