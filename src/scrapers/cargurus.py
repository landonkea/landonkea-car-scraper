# ───────────────────────────────────────────────────────────────────
# CarGurus scraper, Playwright for JS-rendered car search
# ───────────────────────────────────────────────────────────────────
# CarGurus is a car search engine with dealer + private party
# listings. Uses Playwright because the site is JS-heavy.
# ───────────────────────────────────────────────────────────────────

import json
import re
from typing import Optional

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapedListing
from config import Config


class CarGurusScraper(BaseScraper):
    """Scrapes CarGurus for car listings in Arizona."""

    def __init__(self, config: Config):
        super().__init__(config)
        self.source_name = "cargurus"

    def _build_search_url(self) -> str:
        product = self.config.search.product_name
        # CarGurus URL: /Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action
        # Using the search page instead: /Cars/{make}-{model}/filter
        # Fallback to their general search
        query = product.replace(" ", "+")
        return (
            f"https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action"
            f"?zip=85001"  # Phoenix AZ zip
            f"&showNegotiable=true"
            f"&sortDir=ASC"
            f"&sourceContext=carGurusHomePageModel"
            f"&distance=50"
            f"&sortType=PRICE"
            f"&entitySelectingHelper.selectedEntity="
            f"&entitySelectingHelper.selectedEntity2="
        )

    def _fetch_page(self, url: str) -> str:
        """Fetch CarGurus page using Playwright."""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)

                # Try to extract listings from the page
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            raise Exception(f"Playwright failed: {e}") from e

    def _parse_listing(self, card: BeautifulSoup) -> Optional[ScrapedListing]:
        """Parse a CarGurus listing card."""
        # Title / car name
        title_el = card.select_one("[class*='title' i], h4, .cg-dealFinder-result-subtitle")
        if not title_el:
            title_el = card.select_one("a[aria-label]")
        title = ""
        if title_el:
            title = title_el.get("aria-label") or title_el.get_text(strip=True)
        if not title:
            return None

        # Price
        price_el = card.select_one("[class*='price' i], .cg-dealFinder-result-price")
        if not price_el:
            return None
        price_text = price_el.get_text(strip=True)
        price_match = re.search(r'\$?([0-9,]+)', price_text)
        if not price_match:
            return None
        price = float(price_match.group(1).replace(",", ""))
        if price <= 0:
            return None

        # URL
        link_el = card.select_one("a[href]")
        url = ""
        if link_el:
            url = link_el.get("href", "")
            if url and not url.startswith("http"):
                url = f"https://www.cargurus.com{url}"

        # Listing ID from URL
        id_match = re.search(r'/(?:listing|L-)([^/?]+)', url)
        listing_id = id_match.group(1) if id_match else f"url_{hash(url)}"

        # Location
        location_el = card.select_one("[class*='location' i], [class*='dealer' i]")
        location = location_el.get_text(strip=True) if location_el else None

        specs = self.parse_common_specs(title)

        return ScrapedListing(
            source=self.source_name,
            listing_id=f"cargurus-{listing_id}",
            title=title,
            price_usd=price,
            url=url,
            condition="Used",
            location=location,
            year=specs.get("year"),
            make=specs.get("make"),
            model=specs.get("model"),
            mileage=specs.get("mileage"),
            transmission=specs.get("transmission"),
            doors=specs.get("doors"),
            title_status=specs.get("title_status"),
            fuel_type=specs.get("fuel_type"),
        )

    def scrape(self) -> list[ScrapedListing]:
        found: list[ScrapedListing] = []
        found_ids: set = set()
        search_url = self._build_search_url()

        try:
            html = self._fetch_page(search_url)
            soup = self.parse_html(html)

            # Try multiple selector strategies for CarGurus cards
            cards = (
                soup.select("[class*='listing' i]")
                or soup.select("[class*='result' i]")
                or soup.select("[data-testid]")
                or soup.select("article")
            )

            max_results = self.config.search.results_per_size
            for card in cards:
                if len(found) >= max_results:
                    break
                try:
                    listing = self._parse_listing(card)
                    if listing and listing.listing_id not in found_ids:
                        if self.passes_filters(listing):
                            found.append(listing)
                            found_ids.add(listing.listing_id)
                except Exception:
                    continue

        except Exception as e:
            print(f"  [CarGurus] Error: {e}")

        print(f"  [CarGurus] Found {len(found)} matching listings")
        return found
