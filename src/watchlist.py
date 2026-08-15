# ───────────────────────────────────────────────────────────────────
# Watchlist, track specific listings by URL
# ───────────────────────────────────────────────────────────────────
# Entries live in data/watchlist.json. Every run, matched against
# freshly scraped listings. Alerts on price changes or new sightings.
# ───────────────────────────────────────────────────────────────────

import json
import os
from datetime import datetime, timezone

from database import Listing
from notifier import clean_url

DEFAULT_WATCHLIST_PATH = "data/watchlist.json"


def watchlist_path_for_environment(environment: str) -> str:
    if environment == "production":
        return DEFAULT_WATCHLIST_PATH
    root, ext = os.path.splitext(DEFAULT_WATCHLIST_PATH)
    return f"{root}.{environment}{ext}"


def load_watchlist(path: str = DEFAULT_WATCHLIST_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    return data


def save_watchlist(entries: list[dict], path: str = DEFAULT_WATCHLIST_PATH) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")


def _entry_matches(entry: dict, listing: Listing) -> bool:
    if entry.get("source") and entry.get("listing_id"):
        return (
            entry["source"] == listing.source
            and str(entry["listing_id"]) == str(listing.listing_id)
        )
    entry_url = entry.get("url")
    if not entry_url:
        return False
    return clean_url(entry_url) == clean_url(listing.url)


def match_watchlist_entries(
    entries: list[dict], listings: list[Listing]
) -> list[tuple[dict, Listing]]:
    matches: list[tuple[dict, Listing]] = []
    for entry in entries:
        for listing in listings:
            if _entry_matches(entry, listing):
                if not entry.get("source"):
                    entry["source"] = listing.source
                if not entry.get("listing_id"):
                    entry["listing_id"] = listing.listing_id
                matches.append((entry, listing))
                break
    return matches


def find_watchlist_alerts(
    matches: list[tuple[dict, Listing]],
) -> list[tuple[dict, Listing]]:
    alerts = []
    for entry, listing in matches:
        last_price = entry.get("last_alerted_price")
        if last_price is None or float(last_price) != float(listing.price_usd):
            alerts.append((entry, listing))
    return alerts


def record_watchlist_alerts(alerts: list[tuple[dict, Listing]]) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    for entry, listing in alerts:
        entry["last_alerted_price"] = listing.price_usd
        entry["last_alerted_at"] = now_iso
