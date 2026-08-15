# ───────────────────────────────────────────────────────────────────
# Main orchestrator, runs all scrapers, analyzes prices, alerts
# ───────────────────────────────────────────────────────────────────
# Entry point. Loads config, runs every enabled scraper, saves to
# database, scores deals, and sends alerts.
# ───────────────────────────────────────────────────────────────────

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import load_config, Config
from database import (
    get_session,
    Listing,
    prune_old_inactive_listings,
    record_price_history,
    RETENTION_DAYS,
)

from scrapers.base import ScrapedListing
from scrapers.craigslist import CraigslistScraper
from scrapers.offerup import OfferUpScraper
from scrapers.ebay import eBayScraper
from scrapers.cargurus import CarGurusScraper
from scrapers.autotrader import AutoTraderScraper
from scrapers.facebook import FacebookMarketplaceScraper

from price_analyzer import PriceAnalyzer, is_meaningful_price_drop
from notifier import Notifier
from stats_tracker import record_daily_stats
from pages_generator import generate_pages_data
from watchlist import (
    load_watchlist,
    save_watchlist,
    match_watchlist_entries,
    find_watchlist_alerts,
    record_watchlist_alerts,
    watchlist_path_for_environment,
)


SCRAPER_CLASSES = {
    "craigslist": CraigslistScraper,
    "offerup": OfferUpScraper,
    "ebay": eBayScraper,
    "cargurus": CarGurusScraper,
    "autotrader": AutoTraderScraper,
    "facebook": FacebookMarketplaceScraper,
}


def get_enabled_scrapers(config: Config) -> list:
    """Get scraper instances for all enabled sites applicable to the active search."""
    scrapers = []
    product_type = config.search.product_type
    for source_name, scraper_class in SCRAPER_CLASSES.items():
        site_config = getattr(config.sites, source_name, None)
        if not (site_config and site_config.enabled):
            continue
        applicable = site_config.applicable_product_types
        if applicable is not None and product_type not in applicable:
            continue
        scrapers.append(scraper_class(config))
        print(f"  [Setup] Enabled scraper: {source_name}")
    if not scrapers:
        print("  No scrapers enabled. Check config.yaml.")
    return scrapers


def listing_to_db(db, listing: ScrapedListing,
                   config: Config) -> tuple[Listing, Optional[float]]:
    """Save or update a ScrapedListing in the database. Returns (db_obj, old_price)."""
    existing = db.query(Listing).filter(
        Listing.source == listing.source,
        Listing.listing_id == listing.listing_id,
    ).first()

    old_price: Optional[float] = existing.price_usd if existing else None

    if existing:
        existing.title = listing.title
        existing.price_usd = listing.price_usd
        existing.url = listing.url
        existing.condition = listing.condition
        existing.location = listing.location
        existing.year = listing.year
        existing.make = listing.make
        existing.model = listing.model
        existing.mileage = listing.mileage
        existing.transmission = listing.transmission
        existing.doors = listing.doors
        existing.title_status = listing.title_status
        existing.fuel_type = listing.fuel_type
        existing.last_seen_at = datetime.now(timezone.utc)
        existing.is_active = True
        db_obj = existing
    else:
        db_obj = Listing(
            source=listing.source,
            listing_id=listing.listing_id,
            title=listing.title,
            price_usd=listing.price_usd,
            url=listing.url,
            condition=listing.condition,
            location=listing.location,
            year=listing.year,
            make=listing.make,
            model=listing.model,
            mileage=listing.mileage,
            transmission=listing.transmission,
            doors=listing.doors,
            title_status=listing.title_status,
            fuel_type=listing.fuel_type,
        )
        db.add(db_obj)
        db.flush()

    key = config.search.product_type
    threshold = config.price.great_deal_usd.get(key, 5000)
    db_obj.is_great_deal = listing.price_usd <= threshold

    record_price_history(db, db_obj, listing.price_usd)
    db.commit()

    return db_obj, old_price


def find_new_listings(db, scraped: list[ScrapedListing]) -> list[ScrapedListing]:
    """Find listings we haven't seen before."""
    new_listings = []
    for sl in scraped:
        existing = db.query(Listing).filter(
            Listing.source == sl.source,
            Listing.listing_id == sl.listing_id,
        ).first()
        if not existing:
            new_listings.append(sl)
    return new_listings


SCOOPED_DEAL_HOURS = 24


def expire_stale_listings(db, hours: int = 72) -> tuple[int, list[Listing]]:
    """Mark listings inactive if not seen in `hours`. Returns (expired_count, scooped)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stale = (
        db.query(Listing)
        .filter(Listing.is_active == True, Listing.last_seen_at < cutoff)
        .all()
    )
    scooped: list[Listing] = []
    for listing in stale:
        if (
            listing.is_great_deal
            and listing.first_seen_at is not None
            and listing.last_seen_at is not None
            and (listing.last_seen_at - listing.first_seen_at) <= timedelta(hours=SCOOPED_DEAL_HOURS)
        ):
            scooped.append(listing)
        listing.is_active = False
    db.commit()
    return len(stale), scooped


def _run_one_search(
    config: Config,
    search_config,
    db,
    watchlist_entries: Optional[list[dict]] = None,
    watchlist_matches: Optional[list[tuple[dict, Listing]]] = None,
) -> None:
    """Run one product search end-to-end: scrape, save, analyze, alert."""
    if watchlist_entries is None:
        watchlist_entries = []
    if watchlist_matches is None:
        watchlist_matches = []

    product_name = search_config.product_name
    print(f"\n{'─'*60}")
    print(f"  Searching for: {product_name}")
    print(f"  Year: {search_config.min_year}+ | Transmission: {search_config.transmission}")
    print(f"  Max mileage: {search_config.max_mileage:,} | Doors: {search_config.min_doors}+")
    print(f"{'─'*60}\n")

    config.search = search_config
    analyzer = PriceAnalyzer(config)
    notifier = Notifier(config)
    scrapers = get_enabled_scrapers(config)

    print("Scraping marketplaces...")
    all_scraped: list[ScrapedListing] = []
    for scraper in scrapers:
        print(f"\n  -- {scraper.source_name.upper()} --")
        try:
            found = scraper.scrape()
            all_scraped.extend(found)
        except Exception as e:
            print(f"  [FAIL] {scraper.source_name} failed: {e}")
            continue

    print(f"\n  Total raw listings found: {len(all_scraped)}")

    print("\nSaving to database...")
    db_listings: list[Listing] = []
    price_drops: list[tuple[Listing, float]] = []
    for scraped in all_scraped:
        try:
            db_obj, old_price = listing_to_db(db, scraped, config)
            db_listings.append(db_obj)
            if old_price is not None and is_meaningful_price_drop(
                old_price, float(db_obj.price_usd), config
            ):
                price_drops.append((db_obj, old_price))
        except Exception as e:
            print(f"  [DB] Error saving {scraped.title[:50]}: {e}")
            continue

    print(f"  Saved/updated {len(db_listings)} listings")
    if price_drops:
        print(f"  Detected {len(price_drops)} meaningful price drop(s)")

    if watchlist_entries:
        watchlist_matches.extend(
            match_watchlist_entries(watchlist_entries, db_listings)
        )

    stat_rows = record_daily_stats(db, search_config, db_listings)
    if stat_rows:
        print(f"  [Stats] Updated {stat_rows} daily price-stat group(s)")

    print("\nAnalyzing prices...")
    analyzer.analyze(db_listings)
    stats = analyzer.get_stats()

    print(f"  Listings analyzed: {stats['count']}")
    print(f"  Price range: ${stats['min']:,.0f} - ${stats['max']:,.0f}")
    print(f"  Median: ${stats['median']:,.0f} | Mean: ${stats['mean']:,.0f}")

    top_deals = analyzer.get_top_deals()
    if top_deals:
        print(f"\n  Top {len(top_deals)} Deals:")
        for i, l in enumerate(top_deals[:5], 1):
            car_info = f"{l.year or '?'} {l.make or '?'} {l.model or '?'}"
            mileage_str = f"{l.mileage:,}mi" if l.mileage else "?"
            emoji = "!" if l.is_great_deal else "$"
            print(f"    {emoji} #{i}: ${l.price_usd:,.0f} | {car_info} ({mileage_str}) | {l.source} | Score: {l.deal_score}")

    print("\nChecking for new listings...")
    new_listings = find_new_listings(db, all_scraped)
    print(f"  Truly new: {len(new_listings)}")

    print("\nSending alerts...")
    has_great_deals = any(l.is_great_deal for l in top_deals)

    if config.dry_run:
        if new_listings or has_great_deals:
            print(f"  [dry-run] Would send alert for {len(top_deals)} top deal(s), skipped.")
        else:
            print("  No new listings or great deals, skipping alert.")
        if price_drops:
            print(f"  [dry-run] Would send price-drop alert for {len(price_drops)} listing(s), skipped.")
    else:
        if new_listings or has_great_deals:
            notifier.send_alert(top_deals, stats)
        else:
            print("  No new listings or great deals, skipping alert.")
        if price_drops:
            print(f"\nSending price-drop alerts for {len(price_drops)} listing(s)...")
            notifier.send_price_drop_alert(price_drops)


def run_scrape(config: Config) -> int:
    """Run the full scrape cycle."""
    print(f"\n{'='*60}")
    print("  Car Scraper, Starting Run")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Environment: {config.environment}")
    print(f"{'='*60}\n")

    print("Initializing...")
    db = get_session(config.database.url)
    print(f"  [DB] Connected to {config.database.url}")

    expired_count, scooped_deals = expire_stale_listings(db, hours=72)
    print(f"  [DB] Expired {expired_count} listings not seen in 72+ hours")

    if scooped_deals:
        print(f"  {len(scooped_deals)} great deal(s) expired within "
              f"{SCOOPED_DEAL_HOURS}h, likely scooped:")
        for l in scooped_deals:
            print(f"    - ${l.price_usd:,.0f} | {l.source} | {l.title[:60]}")
        if config.dry_run:
            print(f"  [dry-run] Would send scooped-deal alert, skipped.")
        else:
            notifier = Notifier(config)
            notifier.send_scooped_deal_alert(scooped_deals)

    pruned_count = prune_old_inactive_listings(db)
    print(f"  [DB] Pruned {pruned_count} listings inactive for {RETENTION_DAYS}+ days")
    print()

    watchlist_path = watchlist_path_for_environment(config.environment)
    watchlist_entries = load_watchlist(watchlist_path)
    watchlist_matches: list[tuple[dict, Listing]] = []

    for search_config in config.searches:
        _run_one_search(config, search_config, db, watchlist_entries, watchlist_matches)

    if watchlist_entries:
        watchlist_alerts = find_watchlist_alerts(watchlist_matches)
        if watchlist_alerts:
            print(f"\n{len(watchlist_alerts)} watchlist listing(s) newly matched or changed price...")
            if config.dry_run:
                print(f"  [dry-run] Would send watchlist alert, skipped.")
            else:
                notifier = Notifier(config)
                notifier.send_watchlist_alert(watchlist_alerts)
                record_watchlist_alerts(watchlist_alerts)
        if not config.dry_run:
            save_watchlist(watchlist_entries, watchlist_path)

    print("\nUpdating price trend charts...")
    exported_rows = generate_pages_data(db)
    print(f"  [Pages] Exported {exported_rows} daily price-stat rows")

    print(f"\n{'='*60}")
    print(f"  Run complete, {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    print(f"  Total active listings in DB: {db.query(Listing).filter(Listing.is_active == True).count()}")
    print(f"{'='*60}\n")

    return 0


def main():
    """CLI entry point."""
    config_path = "config.yaml"

    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            config_path = sys.argv[idx + 1]

    dry_run = "--dry-run" in sys.argv or "--no-alert" in sys.argv

    print(f"Loading config from: {config_path}")
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        sys.exit(1)

    config = load_config(config_path)
    config.dry_run = dry_run
    if dry_run:
        print("--dry-run set: alerts will be logged but not sent.")

    exit_code = run_scrape(config)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
