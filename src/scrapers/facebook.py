# ───────────────────────────────────────────────────────────────────
# Facebook Marketplace scraper, login-gated via session cookie
# ───────────────────────────────────────────────────────────────────
# Requires FACEBOOK_SESSION_COOKIE to be set. Without it, returns
# no listings (inert stub). Uses Playwright with the cookie to
# load Facebook Marketplace search results.
# ───────────────────────────────────────────────────────────────────

import re
from typing import Optional

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapedListing
from config import Config


class FacebookMarketplaceScraper(BaseScraper):
    """
    Scrapes Facebook Marketplace for car listings.

    Requires a valid Facebook session cookie set via
    FACEBOOK_SESSION_COOKIE environment variable. Without it,
    this scraper returns no listings (stays inert).
    """

    def __init__(self, config: Config):
        super().__init__(config)
        self.source_name = "facebook"

    def _build_search_url(self) -> str:
        query = self.config.search.product_name.replace(" ", "+")
        return f"https://www.facebook.com/marketplace/phoenix/search/?query={query}&exact=false"

    def _get_session_cookie(self) -> Optional[str]:
        """Get the Facebook session cookie from environment."""
        return self.config.secrets.get("facebook_session_cookie")

    def _fetch_page(self, url: str, cookie: str) -> str:
        """Fetch Facebook Marketplace page using Playwright with session cookie."""
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

                # Set the session cookie
                context.add_cookies([{
                    "name": "c_user",
                    "value": cookie,
                    "domain": ".facebook.com",
                    "path": "/",
                }])

                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(8000)
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            raise Exception(f"Playwright failed: {e}") from e

    def _parse_listing(self, card: BeautifulSoup) -> Optional[ScrapedListing]:
        """Parse a Facebook Marketplace listing card."""
        # Title
        title_el = card.select_one("[class*='title' i], span[dir='auto']")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None

        # Price
        price_el = card.select_one("[class*='price' i], span[aria-label]")
        price_text = ""
        if price_el:
            price_text = price_el.get("aria-label", "") or price_el.get_text(strip=True)
        price_match = re.search(r'\$?([0-9,]+)', price_text)
        if not price_match:
            return None
        price = float(price_match.group(1).replace(",", ""))
        if price <= 0:
            return None

        # URL
        link_el = card.select_one("a[href*='/marketplace/item/']")
        url = ""
        if link_el:
            url = link_el.get("href", "")
            if url and not url.startswith("http"):
                url = f"https://www.facebook.com{url}"

        # Listing ID from URL
        id_match = re.search(r'/item/(\d+)', url)
        listing_id = id_match.group(1) if id_match else f"url_{hash(url)}"

        # Location
        location_el = card.select_one("[class*='location' i]")
        location = location_el.get_text(strip=True) if location_el else None

        specs = self.parse_common_specs(title)

        return ScrapedListing(
            source=self.source_name,
            listing_id=f"fb-{listing_id}",
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
        cookie = self._get_session_cookie()
        if not cookie:
            print("  [Facebook] No session cookie set, skipping. "
                  "Set FACEBOOK_SESSION_COOKIE to enable.")
            return []

        found: list[ScrapedListing] = []
        found_ids: set = set()
        search_url = self._build_search_url()

        try:
            html = self._fetch_page(search_url, cookie)
            soup = self.parse_html(html)

            # Facebook Marketplace listing cards
            cards = (
                soup.select("[class*='listing' i]")
                or soup.select("[data-testid]")
                or soup.select("a[href*='/marketplace/item/']")
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
            print(f"  [Facebook] Error: {e}")

        print(f"  [Facebook] Found {len(found)} matching listings")
        return found
