"""Tests for Craigslist scraper.

Covers URL building, price parsing, listing ID extraction, and HTML parsing.
"""
import pytest
from unittest.mock import MagicMock, patch

from scrapers.craigslist import CraigslistScraper


@pytest.fixture
def config():
    """Minimal config for Craigslist scraper tests."""
    cfg = MagicMock()
    cfg.search.product_name = "Honda Fit"
    cfg.search.product_type = "car"
    cfg.search.results_per_size = 30
    cfg.price.absolute_max_usd = 15000
    cfg.sites.craigslist.enabled = True
    cfg.sites.craigslist.regions = None
    cfg.sites.craigslist.applicable_product_types = ["car"]
    cfg.sites.craigslist.base_url = ""
    return cfg


@pytest.fixture
def scraper(config):
    return CraigslistScraper(config)


# ── URL building ────────────────────────────────────────────────────


class TestBuildSearchUrl:
    """_build_search_url constructs the Craigslist search URL."""

    def test_uses_cars_category(self, scraper):
        url = scraper._build_search_url("phoenix")
        assert "cat=cta" in url

    def test_includes_query(self, scraper):
        url = scraper._build_search_url("phoenix")
        assert "query=" in url

    def test_includes_max_price(self, scraper):
        url = scraper._build_search_url("phoenix")
        assert "max_price=15000" in url

    def test_includes_region(self, scraper):
        url = scraper._build_search_url("tucson")
        assert "tucson" in url

    def test_uses_area_path(self, scraper):
        url = scraper._build_search_url("phoenix")
        assert "/search/area/" in url


# ── Price parsing ───────────────────────────────────────────────────


class TestParsePrice:
    """_parse_price extracts numeric price from text."""

    def test_parses_dollar_amount(self, scraper):
        assert scraper._parse_price("$7,500") == 7500.0

    def test_parses_without_dollar_sign(self, scraper):
        assert scraper._parse_price("7500") == 7500.0

    def test_parses_with_commas(self, scraper):
        assert scraper._parse_price("$12,500") == 12500.0

    def test_parses_decimal(self, scraper):
        assert scraper._parse_price("$7,500.50") == 7500.5

    def test_returns_none_for_empty(self, scraper):
        assert scraper._parse_price("") is None

    def test_returns_none_for_no_number(self, scraper):
        assert scraper._parse_price("no price") is None

    def test_handles_whitespace(self, scraper):
        assert scraper._parse_price("  $7,500  ") == 7500.0


# ── Listing ID ──────────────────────────────────────────────────────


class TestGetListingId:
    """_get_listing_id extracts a unique ID from the listing URL."""

    def test_extracts_last_segment(self, scraper):
        url = "https://phoenix.craigslist.org/cph/cto/7854321012.html"
        lid = scraper._get_listing_id(url)
        assert lid == "craigslist-7854321012.html"

    def test_strips_trailing_slash(self, scraper):
        url = "https://phoenix.craigslist.org/cph/cto/7854321012/"
        lid = scraper._get_listing_id(url)
        assert "7854321012" in lid

    def test_falls_back_to_hash(self, scraper):
        url = "https://phoenix.craigslist.org/search/cta"
        lid = scraper._get_listing_id(url)
        assert lid.startswith("craigslist-")


# ── Regions ─────────────────────────────────────────────────────────


class TestRegions:
    """regions property returns configured or default regions."""

    def test_uses_default_when_none(self, scraper):
        assert scraper.regions == ["phoenix"]

    def test_uses_configured_regions(self, config):
        config.sites.craigslist.regions = ["phoenix", "tucson"]
        scraper = CraigslistScraper(config)
        assert scraper.regions == ["phoenix", "tucson"]


# ── Parse single item ──────────────────────────────────────────────


class TestParseSingleItem:
    """_parse_single_item extracts a ScrapedListing from an HTML element."""

    def _make_element(self, title="2018 Honda Fit LX", price="$7,500",
                      url="https://craigslist.org/cto/123.html",
                      location="Phoenix"):
        """Create a mock BeautifulSoup element."""
        el = MagicMock()
        title_el = MagicMock()
        title_el.get_text.return_value = title
        el.select_one.return_value = None

        def select_side_effect(selector):
            if selector == "div.title":
                return title_el
            if selector == "a":
                link = MagicMock()
                link.get.return_value = url
                return link
            if selector == "div.price":
                price_el = MagicMock()
                price_el.get_text.return_value = price
                return price_el
            if selector == "div.location":
                loc_el = MagicMock()
                loc_el.get_text.return_value = location
                return loc_el
            return None

        el.select_one.side_effect = select_side_effect
        return el

    def test_parses_valid_item(self, scraper):
        el = self._make_element()
        listing = scraper._parse_single_item(el)
        assert listing is not None
        assert listing.title == "2018 Honda Fit LX"
        assert listing.price_usd == 7500.0
        assert listing.source == "craigslist"

    def test_returns_none_for_empty_title(self, scraper):
        el = self._make_element(title="")
        assert scraper._parse_single_item(el) is None

    def test_returns_none_for_no_price(self, scraper):
        el = MagicMock()
        title_el = MagicMock()
        title_el.get_text.return_value = "2018 Honda Fit"
        price_el = None

        def select_side_effect(selector):
            if selector == "div.title":
                return title_el
            if selector == "div.price":
                return price_el
            if selector == "a":
                link = MagicMock()
                link.get.return_value = "https://craigslist.org/cto/123.html"
                return link
            return None

        el.select_one.side_effect = select_side_effect
        assert scraper._parse_single_item(el) is None

    def test_extracts_year_from_title(self, scraper):
        el = self._make_element(title="2018 Honda Fit LX")
        listing = scraper._parse_single_item(el)
        assert listing.year == 2018

    def test_extracts_make_from_title(self, scraper):
        el = self._make_element(title="2018 Honda Fit LX")
        listing = scraper._parse_single_item(el)
        assert listing.make == "Honda"
