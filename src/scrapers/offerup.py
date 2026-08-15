# ───────────────────────────────────────────────────────────────────
# OfferUp scraper, Playwright + __NEXT_DATA__ extraction
# ───────────────────────────────────────────────────────────────────
# OfferUp is a React app with anti-bot protection. Uses Playwright
# to load the page and extracts listing data from Next.js embedded
# JSON or DOM elements.
# ───────────────────────────────────────────────────────────────────

import json
import re
from typing import Optional

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapedListing
from config import Config


class OfferUpScraper(BaseScraper):
    """Scrapes OfferUp for car listings using Playwright."""

    def __init__(self, config: Config):
        super().__init__(config)
        self.source_name = "offerup"

    def _build_search_url(self) -> str:
        query = self.config.search.product_name
        encoded = query.replace(" ", "+")
        return f"https://offerup.com/search/?q={encoded}"

    def _build_fallback_urls(self, url: str) -> list[str]:
        urls_to_try = [url]
        product = self.config.search.product_name
        specific_query = f"{product} car"
        fallback_url = f"https://offerup.com/search/?q={specific_query.replace(' ', '+')}"
        urls_to_try.append(fallback_url)
        return urls_to_try

    def _fetch_listings_json(self, url: str) -> list[dict]:
        from playwright.sync_api import sync_playwright

        urls_to_try = self._build_fallback_urls(url)
        last_error = None

        try:
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

                for i, try_url in enumerate(urls_to_try):
                    if i > 0:
                        print(f"  [OfferUp] Trying fallback URL: {try_url[:80]}")
                    page.goto(try_url, wait_until="load", timeout=30000)
                    page.wait_for_timeout(5000)

                    listings = self._try_next_data(page)
                    if listings:
                        browser.close()
                        return listings

                    page.wait_for_timeout(8000)
                    html = page.content()
                    soup = BeautifulSoup(html, "lxml")

                    listings = self._try_json_ld(soup)
                    if listings:
                        browser.close()
                        return listings

                    listings = self._try_rendered_dom(soup)
                    if listings:
                        browser.close()
                        return listings

                    listings = self._try_html_links(soup)
                    if listings:
                        browser.close()
                        return listings

                browser.close()
        except Exception as e:
            last_error = e

        if last_error:
            raise Exception(
                f"Playwright error: {last_error}. "
                f"Install: pip install playwright && playwright install chromium"
            ) from last_error

        print("  [OfferUp] No listings found on page")
        return []

    def _try_next_data(self, page) -> list[dict]:
        next_data_json = page.evaluate("""
            () => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.textContent : null;
            }
        """)
        if not next_data_json:
            return []
        data = json.loads(next_data_json)
        page_props = data.get("props", {}).get("pageProps", {})
        feed = page_props.get("searchFeedResponse", {})
        loose_tiles = feed.get("looseTiles", [])
        listings = []
        for tile in loose_tiles:
            if tile.get("__typename") == "ModularFeedTileListing":
                listing_data = tile.get("listing", {})
                if listing_data and listing_data.get("title"):
                    listings.append(listing_data)
        return listings

    def _try_json_ld(self, soup: BeautifulSoup) -> list[dict]:
        scripts = soup.select("script[type='application/ld+json']")
        listings = []
        for script in scripts:
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    name = item.get("name", "")
                    product_lower = self.config.search.product_name.lower()
                    if product_lower.split()[0] not in name.lower():
                        continue
                    url = item.get("url", "")
                    url = self._clean_url(url)
                    id_match = re.search(r'/item/detail/([^/?]+)', url)
                    listing_id = id_match.group(1) if id_match else ""
                    offers = item.get("offers", {})
                    price_str = "0"
                    if isinstance(offers, dict):
                        price_str = offers.get("price", "0")
                    elif isinstance(offers, list) and offers:
                        price_str = offers[0].get("price", "0")
                    listings.append({
                        "listingId": listing_id,
                        "title": name,
                        "price": str(price_str),
                        "conditionText": item.get("condition", ""),
                        "locationName": item.get("areaServed", ""),
                        "url": url,
                    })
            except Exception:
                continue
        return listings

    def _try_rendered_dom(self, soup: BeautifulSoup) -> list[dict]:
        cards = (
            soup.select("[data-testid='search-card']")
            or soup.select("article")
            or soup.select("div[class*='Card' i]")
            or soup.select("a[href*='/item/detail/']")
        )
        seen_ids = set()
        listings = []
        product_lower = self.config.search.product_name.lower().split()[0]
        for card in cards:
            try:
                title = ""
                title_el = card.select_one(
                    "h1, h2, h3, [class*='title' i], [class*='Title'], [aria-label]"
                )
                if title_el:
                    title = title_el.get("aria-label") or title_el.get_text(strip=True) or ""
                if not title:
                    title = card.get("aria-label") or card.get_text(strip=True) or ""
                if not title or product_lower not in title.lower():
                    continue

                price_el = card.select_one(
                    "[class*='price' i], [class*='Price'], [data-testid*='price']"
                )
                price_str = price_el.get_text(strip=True) if price_el else "0"
                price_str = re.sub(r'[$,]', '', price_str)
                price = float(price_str) if price_str else 0
                if price <= 0:
                    continue

                link = card if card.name == "a" else card.select_one("a[href*='/item/detail/']")
                url = ""
                if link:
                    url = link.get("href", "")
                    if url and not url.startswith("http"):
                        url = f"https://offerup.com{url}"
                    url = self._clean_url(url)

                id_match = re.search(r'/item/detail/([^/?]+)', url)
                listing_id = id_match.group(1) if id_match else ""
                if not listing_id or listing_id in seen_ids:
                    continue
                seen_ids.add(listing_id)

                condition_el = card.select_one("[class*='condition' i], [class*='Condition']")
                condition = condition_el.get_text(strip=True) if condition_el else None

                location_el = card.select_one("[class*='location' i], [class*='Location']")
                location = location_el.get_text(strip=True) if location_el else None

                listings.append({
                    "listingId": listing_id,
                    "title": title,
                    "price": str(price),
                    "conditionText": condition,
                    "locationName": location,
                    "url": url,
                })
            except Exception:
                continue
        return listings

    def _try_html_links(self, soup: BeautifulSoup) -> list[dict]:
        links = soup.select("a[href*='/item/detail/']")
        seen_ids = set()
        listings = []
        product_lower = self.config.search.product_name.lower().split()[0]
        for link in links:
            href = link.get("href", "")
            if not href:
                continue
            if href.startswith("/"):
                href = f"https://offerup.com{href}"
            href = self._clean_url(href)
            id_match = re.search(r'/item/detail/([^/?]+)', href)
            if not id_match:
                continue
            listing_id = id_match.group(1)
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)
            title = link.get("aria-label", "") or link.get_text(strip=True) or ""
            if product_lower not in title.lower():
                continue
            price = "0"
            parent = link.parent
            if parent:
                price_el = parent.select_one(
                    "[class*='price' i], [class*='Price'], [data-testid*='price']"
                )
                if price_el:
                    price = re.sub(r'[$,]', '', price_el.get_text(strip=True))
            listings.append({
                "listingId": listing_id,
                "title": title,
                "price": price,
                "conditionText": None,
                "locationName": None,
                "url": href,
            })
        return listings

    @staticmethod
    def _clean_url(url: str) -> str:
        url = re.sub(r'\?.*', '', url)
        url = re.sub(r'#.*', '', url)
        return url

    def _parse_listing(self, item: dict) -> Optional[ScrapedListing]:
        title = item.get("title", "")
        if not title:
            return None

        price_str = item.get("price", "0")
        if isinstance(price_str, str):
            price_str = price_str.replace("$", "").replace(",", "")
        try:
            price = float(price_str)
        except (ValueError, TypeError):
            return None
        if price <= 0:
            return None

        listing_id = item.get("listingId", "")
        if not listing_id:
            return None

        url = f"https://offerup.com/item/detail/{listing_id}"
        url = self._clean_url(url)

        condition = item.get("conditionText") or "Used"
        location = item.get("locationName") or item.get("location", "")

        specs = self.parse_common_specs(title)

        return ScrapedListing(
            source=self.source_name,
            listing_id=listing_id,
            title=title,
            price_usd=price,
            url=url,
            condition=condition,
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
            listings_data = self._fetch_listings_json(search_url)
            max_results = self.config.search.results_per_size
            for item in listings_data:
                if len(found) >= max_results:
                    break
                try:
                    listing = self._parse_listing(item)
                    if listing and listing.listing_id not in found_ids:
                        if self.passes_filters(listing):
                            found.append(listing)
                            found_ids.add(listing.listing_id)
                except Exception:
                    continue
        except Exception as e:
            print(f"  [OfferUp] Error: {e}")

        if found:
            print(f"  [OfferUp] Found {len(found)} matching listings")
        else:
            print("  [OfferUp] No matching listings found.")
        return found
