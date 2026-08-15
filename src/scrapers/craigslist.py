# ───────────────────────────────────────────────────────────────────
# Craigslist scraper, fetches car listings from craigslist.org
# ───────────────────────────────────────────────────────────────────
# Uses cat=cta (cars+trucks) instead of cat=sss (all for sale).
# Config-driven multi-region via config.sites.craigslist.regions.
# Arizona default regions: phoenix, tucson.
# ───────────────────────────────────────────────────────────────────

import re
from typing import Optional
from urllib.parse import quote

from scrapers.base import BaseScraper, ScrapedListing
from config import Config


class CraigslistScraper(BaseScraper):
    """
    Scraper for Craigslist car listings.

    Uses the consolidated /search/area/{region} URL shape with
    cat=cta for the cars+trucks category. Region list is config-driven.
    """

    BASE_URL = "https://www.craigslist.org"
    CATEGORY = "cta"  # cars+trucks, not sss (all for sale)
    DEFAULT_REGIONS = ["phoenix"]

    def __init__(self, config: Config):
        super().__init__(config)
        self.source_name = "craigslist"

    @property
    def regions(self) -> list[str]:
        site_config = self.config.sites.craigslist
        if site_config.regions:
            return list(site_config.regions)
        # Use locations from config
        if self.config.locations:
            all_regions = []
            for loc in self.config.locations:
                all_regions.extend(loc.regions)
            return all_regions if all_regions else list(self.DEFAULT_REGIONS)
        return list(self.DEFAULT_REGIONS)

    def _build_search_url(self, region: str) -> str:
        query = quote(self.config.search.product_name)
        max_price = int(self.config.price.absolute_max_usd)
        return (
            f"{self.BASE_URL}/search/area/{region}"
            f"?cat={self.CATEGORY}&query={query}&max_price={max_price}"
        )

    def _parse_price(self, text: str) -> Optional[float]:
        cleaned = text.replace("$", "").replace(",", "").strip()
        match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        if match:
            return float(match.group(1))
        return None

    def _get_listing_id(self, url: str) -> str:
        segment = url.rstrip("/").rsplit("/", 1)[-1]
        if segment:
            return f"craigslist-{segment}"
        return f"craigslist-url_{hash(url)}"

    def _parse_single_item(self, item) -> Optional[ScrapedListing]:
        title_el = item.select_one("div.title")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None

        link_el = item.select_one("a")
        url = link_el.get("href", "") if link_el else ""
        if not url:
            return None

        price_el = item.select_one("div.price")
        if not price_el:
            return None
        price = self._parse_price(price_el.get_text())
        if price is None:
            return None

        location_el = item.select_one("div.location")
        location = location_el.get_text(strip=True) if location_el else None

        # Detect dealer vs private party
        seller_type = "private_party"
        item_text = item.get_text(strip=True).lower()
        if "dealer" in item_text or "dealership" in item_text:
            seller_type = "dealer"

        listing_id = self._get_listing_id(url)
        specs = self.parse_common_specs(title)

        listing = ScrapedListing(
            source=self.source_name,
            listing_id=listing_id,
            title=title,
            price_usd=price,
            url=url,
            condition=None,
            location=location,
            year=specs.get("year"),
            make=specs.get("make"),
            model=specs.get("model"),
            mileage=specs.get("mileage"),
            transmission=specs.get("transmission"),
            doors=specs.get("doors"),
            title_status=specs.get("title_status"),
            fuel_type=specs.get("fuel_type"),
            seller_type=seller_type,
        )
        return self.enrich_with_vin(listing)

    def _fetch_cards(self, region: str) -> list:
        url = self._build_search_url(region)
        try:
            html = self.fetch_page(url)
        except Exception as e:
            print(f"  [Craigslist] Failed to fetch region={region}: {e}")
            return []
        soup = self.parse_html(html)
        return soup.select("li.cl-static-search-result")

    def scrape(self) -> list[ScrapedListing]:
        found: list[ScrapedListing] = []
        found_ids: set = set()
        max_results = self.config.search.results_per_size

        for region in self.regions:
            if len(found) >= max_results:
                break
            cards = self._fetch_cards(region)
            region_count = 0
            for item in cards:
                if len(found) >= max_results:
                    break
                try:
                    listing = self._parse_single_item(item)
                    if listing and listing.listing_id not in found_ids:
                        if self.passes_filters(listing):
                            found.append(listing)
                            found_ids.add(listing.listing_id)
                            region_count += 1
                except Exception:
                    continue
            print(f"  [Craigslist] region={region}: {region_count} matching listings")

        print(f"  [Craigslist] Found {len(found)} matching listings total "
              f"(regions={','.join(self.regions)})")
        return found
