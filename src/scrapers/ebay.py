# ───────────────────────────────────────────────────────────────────
# eBay Motors scraper, Playwright + car-specific queries
# ───────────────────────────────────────────────────────────────────
# Searches eBay for Buy It Now car listings. Uses Playwright with
# homepage warm-up to bypass bot detection.
# ───────────────────────────────────────────────────────────────────

import re
from typing import Optional

from scrapers.base import BaseScraper, ScrapedListing
from config import Config


class eBayScraper(BaseScraper):
    """Scrapes eBay for car listings."""

    def __init__(self, config: Config):
        super().__init__(config)
        self.source_name = "ebay"

    def _build_search_url(self) -> str:
        product = self.config.search.product_name
        max_price = int(self.config.price.absolute_max_usd)
        # Simplify query: just "2015 honda fit" not the full product_name with parens
        min_year = self.config.search.min_year
        # Extract make/model from product_name (e.g. "Honda Fit (2015+, automatic)" -> "Honda Fit")
        import re as _re
        simple_name = _re.sub(r'\s*\(.*', '', product)
        query = f"{min_year} {simple_name}"

        encoded_query = query.replace(" ", "+")

        # Used / Pre-Owned condition codes, Buy It Now, price ascending
        url = (
            f"https://www.ebay.com/sch/i.html"
            f"?_nkw={encoded_query}"
            f"&LH_ItemCondition=4|3|2|1500|1000|2000"
            f"&_sop=15"
            f"&_udlo=500"
            f"&_udhi={max_price}"
            f"&LH_BIN=1"
            f"&_ipg=120"
        )
        return url

    def _parse_listing_id(self, url: str) -> str:
        match = re.search(r'/itm/(\d+)', url)
        if match:
            return match.group(1)
        match = re.search(r'/p/(\d+)', url)
        if match:
            return f"p_{match.group(1)}"
        return f"url_{hash(url)}"

    def _fetch_listings_html(self, search_url: str) -> str:
        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth
            stealth = Stealth()
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
                stealth.apply_stealth_sync(context)
                page = context.new_page()
                page.goto("https://www.ebay.com", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(3000)
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            raise Exception(f"Playwright failed: {e}") from e

    def _parse_single_item(self, item) -> Optional[ScrapedListing]:
        title_elem = item.select_one(".s-card__title")
        link_elem = item.select_one(".su-card-container__header a.s-card__link")
        price_elem = item.select_one(".s-card__price")
        condition_elem = item.select_one(".s-card__subtitle")

        if not title_elem or not link_elem:
            title_elem = item.select_one(".s-item__title")
            link_elem = item.select_one("a.s-item__link")
            price_elem = item.select_one(".s-item__price")
            condition_elem = item.select_one(".s-item__subtitle")

        if not title_elem or not link_elem:
            return None

        title = title_elem.get_text(strip=True)
        url = link_elem.get("href", "")

        # Clean up eBay title artifacts
        title = re.sub(r'\s*opens\s*(?:in\s*(?:a\s*)?new\s*(?:tab|window))?\s*$', '', title, flags=re.IGNORECASE).strip()
        title = re.sub(r'opens\s*$', '', title, flags=re.IGNORECASE).strip()
        title = re.sub(r'lxopens', 'lx', title, flags=re.IGNORECASE).strip()
        title = re.sub(r'(\w)opens\b', r'\1', title, flags=re.IGNORECASE).strip()
        title = re.sub(r'\s+', ' ', title)  # normalize whitespace

        if not title or "Shop on eBay" in title or "contact seller" in title.lower():
            return None
        if not price_elem:
            return None

        price_text = price_elem.get_text(strip=True)
        price_match = re.search(r'\$?([0-9,]+(?:\.[0-9]{2})?)', price_text)
        if not price_match:
            return None

        price = float(price_match.group(1).replace(",", ""))
        if "bid" in item.get_text(strip=True).lower():
            return None

        listing_id = self._parse_listing_id(url)
        condition = condition_elem.get_text(strip=True) if condition_elem else None
        specs = self.parse_common_specs(title)

        listing = ScrapedListing(
            source=self.source_name,
            listing_id=listing_id,
            title=title,
            price_usd=price,
            url=url,
            condition=condition,
            location=None,
            year=specs.get("year"),
            make=specs.get("make"),
            model=specs.get("model"),
            mileage=specs.get("mileage"),
            transmission=specs.get("transmission"),
            doors=specs.get("doors"),
            title_status=specs.get("title_status"),
            fuel_type=specs.get("fuel_type"),
        )
        return self.enrich_with_vin(listing)

    def scrape(self) -> list[ScrapedListing]:
        found: list[ScrapedListing] = []
        found_ids: set = set()
        search_url = self._build_search_url()
        html = None

        try:
            html = self._fetch_listings_html(search_url)
        except Exception as e:
            print(f"  [eBay] Playwright failed: {e}, trying plain request...")
            try:
                html = self.fetch_page(search_url)
            except Exception as e2:
                print(f"  [eBay] Plain request also failed: {e2}")

        if not html:
            print("  [eBay] No HTML retrieved")
            return found

        soup = self.parse_html(html)
        items = soup.select("li.s-card") or soup.select("div.s-card") or soup.select("li.s-item") or soup.select(".s-item__wrapper")

        max_results = self.config.search.results_per_size
        for item in items:
            if len(found) >= max_results:
                break
            try:
                listing = self._parse_single_item(item)
                if listing and listing.listing_id not in found_ids:
                    if self.passes_filters(listing):
                        found.append(listing)
                        found_ids.add(listing.listing_id)
            except Exception:
                continue

        print(f"  [eBay] Found {len(found)} matching listings")
        return found
