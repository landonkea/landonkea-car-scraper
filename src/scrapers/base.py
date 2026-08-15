# ───────────────────────────────────────────────────────────────────
# Base scraper class, every marketplace scraper inherits from this
# ───────────────────────────────────────────────────────────────────
# Provides HTTP session with rate limiting, user-agent rotation,
# Playwright support, and the passes_filters() pipeline that
# delegates to the active ProductTypeHandler.
# ───────────────────────────────────────────────────────────────────

import random
import time
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from config import Config
from product_types import PRODUCT_TYPES


@dataclass
class ScrapedListing:
    """One listing found on a marketplace. Every scraper returns these."""
    source: str
    listing_id: str
    title: str
    price_usd: float
    url: str
    condition: Optional[str]
    location: Optional[str] = None
    # ── Car-specific fields ─────────────────────────────────────
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    mileage: Optional[int] = None
    transmission: Optional[str] = None
    doors: Optional[int] = None
    title_status: Optional[str] = None
    fuel_type: Optional[str] = None
    seller_type: Optional[str] = None  # "dealer" or "private_party"
    vin: Optional[str] = None
    # ── Electronics-shaped stubs (always None for car listings) ──
    # Present so scrapers using parse_common_specs() don't KeyError
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    screen_size: Optional[float] = None
    chip: Optional[str] = None
    cpu_cores: Optional[int] = None
    gpu_cores: Optional[int] = None


class BaseScraper(ABC):
    """
    Every marketplace scraper must:
      1. Set self.source_name (e.g. "craigslist")
      2. Set self.config (the global config)
      3. Implement scrape() to return list[ScrapedListing]
    """

    def __init__(self, config: Config):
        self.config = config
        self.source_name = "base"
        self.session = requests.Session()
        self._user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        ]
        self._update_headers()

    def _update_headers(self):
        ua = random.choice(self._user_agents)
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Not/A)Brand";v="99", "Google Chrome";v="125", "Chromium";v="125"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Dnt": "1",
            "Connection": "keep-alive",
        })

    def fetch_with_playwright(self, url: str, timeout: int = 30000) -> str:
        """Fetch a page using Playwright headless Chromium."""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                page.wait_for_timeout(3000)
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            raise Exception(f"Playwright failed: {e}") from e

    def fetch_page(self, url: str, max_retries: int = 3) -> str:
        """Fetch a web page with rate limiting and retry/backoff."""
        last_exception: Optional[Exception] = None
        for attempt in range(max_retries):
            self._update_headers()
            delay = 1.5 + random.random()
            time.sleep(delay)
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code == 403:
                    print(f"  [{self.source_name}] 403 on attempt {attempt + 1}, retrying...")
                    last_exception = requests.HTTPError(f"403 Forbidden: {url}")
                    time.sleep(2)
                    continue
                response.raise_for_status()
                return response.text
            except requests.Timeout:
                print(f"  [{self.source_name}] Timeout on attempt {attempt + 1}, retrying...")
                last_exception = requests.Timeout(f"Timeout: {url}")
                time.sleep(2)
                continue
            except requests.ConnectionError as e:
                print(f"  [{self.source_name}] Connection error on attempt {attempt + 1}, retrying...")
                last_exception = e
                time.sleep(3)
                continue
            except requests.HTTPError as e:
                if attempt < max_retries - 1:
                    print(f"  [{self.source_name}] HTTP {e.response.status_code} on attempt {attempt + 1}")
                    time.sleep(2)
                    last_exception = e
                    continue
                raise
        raise last_exception or requests.RequestException(f"Failed after {max_retries} attempts: {url}")

    def parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def parse_common_specs(self, title: str) -> dict:
        """Parse all common specs from a title via the active ProductTypeHandler."""
        handler = PRODUCT_TYPES[self.config.search.product_type]
        return handler.parse_specs(title)

    def enrich_with_vin(self, listing: ScrapedListing) -> ScrapedListing:
        """
        If a VIN is found in the listing title, decode it and fill in
        missing make/model/year/transmission/fuel_type fields.
        """
        from vin_decoder import extract_vin_from_text, decode_vin

        vin = extract_vin_from_text(listing.title)
        if not vin:
            return listing

        listing.vin = vin
        decoded = decode_vin(vin)
        if not decoded:
            return listing

        # Only fill fields that are missing or empty
        if not listing.make and decoded.get("make"):
            listing.make = decoded["make"]
        if not listing.model and decoded.get("model"):
            listing.model = decoded["model"]
        if not listing.year and decoded.get("year"):
            listing.year = decoded["year"]
        if not listing.transmission and decoded.get("transmission"):
            listing.transmission = decoded["transmission"]
        if not listing.fuel_type and decoded.get("fuel_type"):
            listing.fuel_type = decoded["fuel_type"]

        return listing

    def passes_filters(self, listing: ScrapedListing) -> bool:
        """Check if a listing matches our search criteria."""
        s = self.config.search
        handler = PRODUCT_TYPES[s.product_type]

        if not handler.is_relevant(listing.title, s, listing.condition):
            return False
        if not handler.passes_type_filters(listing, s):
            return False
        if s.location and listing.location:
            if s.location.lower() not in listing.location.lower():
                return False
        if listing.price_usd < handler.min_price_usd(s):
            return False
        if listing.price_usd > self.config.price.absolute_max_usd:
            return False
        return True

    @abstractmethod
    def scrape(self) -> list[ScrapedListing]:
        """Scrape the marketplace and return matching listings."""
        pass
