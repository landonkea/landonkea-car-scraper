# ───────────────────────────────────────────────────────────────────
# CarGurus scraper, uses JSON API with Playwright stealth
# ───────────────────────────────────────────────────────────────────
# CarGurus blocks headless browsers. Uses playwright-stealth to
# bypass detection and fetches their searchResults.action JSON API.
# ───────────────────────────────────────────────────────────────────

import json
import re
from typing import Optional

from scrapers.base import BaseScraper, ScrapedListing
from config import Config


# CarGurus entity IDs for each car model
ENTITY_IDS = {
    "honda fit": "d744",
    "chevy spark": "d906",
    "chevrolet spark": "d906",
    "nissan versa": "d262",
    "kia rio": "d159",
}


class CarGurusScraper(BaseScraper):
    """Scrapes CarGurus for car listings in Arizona via JSON API."""

    def __init__(self, config: Config):
        super().__init__(config)
        self.source_name = "cargurus"

    def _get_entity_id(self) -> str:
        """Get the CarGurus entity ID for the current search."""
        product = self.config.search.product_name.lower()
        for key, entity_id in ENTITY_IDS.items():
            if key in product:
                return entity_id
        return ""

    def _fetch_json_listings(self) -> list[dict]:
        """Fetch listings from CarGurus JSON API using Playwright stealth."""
        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth
            stealth = Stealth()

            entity_id = self._get_entity_id()
            min_year = self.config.search.min_year
            max_price = int(self.config.price.absolute_max_usd)

            # Get zip codes from locations config
            zip_codes = [loc.zip for loc in self.config.locations] if self.config.locations else ["85001"]

            all_listings = []
            for zip_code in zip_codes:
                api_url = (
                    f"https://www.cargurus.com/Cars/searchResults.action"
                    f"?zip={zip_code}"
                    f"&inventorySearchWidgetType=AUTO"
                    f"&sortDir=ASC"
                    f"&sortType=PRICE"
                    f"&offset=0"
                    f"&maxResults=100"
                    f"&filtersModified=true"
                    f"&entitySelectingHelper.selectedEntity={entity_id}"
                )

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                stealth.apply_stealth_sync(context)
                page = context.new_page()

                # Navigate to the API endpoint
                page.goto(api_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)

                # Get the JSON content from the page body
                content = page.evaluate("() => document.body.innerText")

                # Parse JSON
                if content.strip().startswith("["):
                    all_listings.extend(json.loads(content))

            browser.close()
            return all_listings

        except Exception as e:
            print(f"  [CarGurus] Playwright/API failed: {e}")
            return []

    def _parse_json_listing(self, item: dict) -> Optional[ScrapedListing]:
        """Parse a CarGurus JSON listing into a ScrapedListing."""
        try:
            title = item.get("listingTitle", "")
            if not title:
                return None

            price = item.get("price", 0)
            if price <= 0:
                return None

            # Filter by year
            year = item.get("carYear", 0)
            if year and year < self.config.search.min_year:
                return None

            # Build URL
            listing_id = item.get("id", "")
            url = f"https://www.cargurus.com/Cars/details/{listing_id}"

            # Extract mileage
            mileage_data = item.get("unitMileage", {})
            mileage = int(mileage_data.get("value", 0)) if mileage_data.get("value") else None

            # Get transmission
            transmission = item.get("localizedTransmission", "")
            if "automatic" in transmission.lower() or "cvt" in transmission.lower():
                transmission = "Automatic"
            elif "manual" in transmission.lower():
                transmission = "Manual"
            else:
                transmission = None

            # Get location
            city = item.get("sellerCity", "")
            region = item.get("sellerRegion", "")
            location = f"{city}, {region}" if city else None

            # Detect dealer vs private party
            seller_type = item.get("sellerType", "").upper()
            if seller_type == "DEALER":
                seller_type = "dealer"
            elif seller_type == "PRIVATE_PARTY":
                seller_type = "private_party"
            else:
                seller_type = "dealer"  # CarGurus is mostly dealers

            # Get make/model
            make = item.get("makeName", "")
            model = item.get("modelName", "")

            specs = self.parse_common_specs(title)

            return ScrapedListing(
                source=self.source_name,
                listing_id=f"cargurus-{listing_id}",
                title=title,
                price_usd=float(price),
                url=url,
                condition="Used",
                location=location,
                year=specs.get("year") or year,
                make=specs.get("make") or make,
                model=specs.get("model") or model,
                mileage=specs.get("mileage") or mileage,
                transmission=specs.get("transmission") or transmission,
                doors=specs.get("doors"),
                title_status=specs.get("title_status"),
                fuel_type=specs.get("fuel_type"),
                seller_type=seller_type,
            )
        except Exception:
            return None

    def scrape(self) -> list[ScrapedListing]:
        found: list[ScrapedListing] = []
        found_ids: set = set()

        # Fetch JSON listings from API
        json_listings = self._fetch_json_listings()
        print(f"  [CarGurus] API returned {len(json_listings)} raw listings")

        max_results = self.config.search.results_per_size
        for item in json_listings:
            if len(found) >= max_results:
                break
            try:
                listing = self._parse_json_listing(item)
                if listing and listing.listing_id not in found_ids:
                    if self.passes_filters(listing):
                        found.append(listing)
                        found_ids.add(listing.listing_id)
            except Exception:
                continue

        print(f"  [CarGurus] Found {len(found)} matching listings")
        return found
