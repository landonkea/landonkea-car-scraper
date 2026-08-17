"""Tests for price analyzer.

Covers deal scoring, suspicious price detection, top deals, and stats.
"""
import pytest
from unittest.mock import MagicMock

from price_analyzer import PriceAnalyzer, is_meaningful_price_drop, format_score_breakdown
from database import Listing


@pytest.fixture
def config():
    """Minimal config for price analyzer tests."""
    cfg = MagicMock()
    cfg.price.absolute_max_usd = 15000
    cfg.price.great_deal_usd = {"car": 6000}
    cfg.price.good_deal_usd = {"car": 8000}
    cfg.price.top_deals_count = 5
    cfg.price.suspicious_price_ratio = 0.5
    cfg.price.suspicious_min_sample = 3
    cfg.price.source_reliability = {}
    cfg.search.product_type = "car"
    cfg.search.min_year = 2015
    cfg.search.max_mileage = 150000
    cfg.search.transmission = "automatic"
    cfg.search.min_doors = 4
    cfg.search.title_status = "clean"
    cfg.search.preferred_brands = []
    cfg.price_drop.enabled = True
    cfg.price_drop.min_drop_percent = 5
    cfg.price_drop.min_drop_usd = 50
    return cfg


def _make_listing(**kwargs):
    """Create a Listing with sensible defaults."""
    defaults = {
        "source": "craigslist",
        "listing_id": "test-123",
        "title": "2018 Honda Fit LX",
        "price_usd": 7500,
        "url": "https://example.com/123",
        "condition": None,
        "location": "Phoenix",
        "year": 2018,
        "make": "Honda",
        "model": "Fit",
        "mileage": 60000,
        "transmission": "Automatic",
        "doors": 4,
        "title_status": "Clean",
        "fuel_type": None,
        "deal_score": None,
        "is_great_deal": False,
    }
    defaults.update(kwargs)
    listing = MagicMock(spec=Listing)
    for k, v in defaults.items():
        setattr(listing, k, v)
    return listing


# ── Stats ───────────────────────────────────────────────────────────


class TestGetStats:
    """get_stats returns price statistics for the batch."""

    def test_empty_listings(self, config):
        analyzer = PriceAnalyzer(config)
        stats = analyzer.get_stats()
        assert stats["count"] == 0

    def test_single_listing(self, config):
        analyzer = PriceAnalyzer(config)
        analyzer.add_listings([_make_listing(price_usd=5000)])
        stats = analyzer.get_stats()
        assert stats["count"] == 1
        assert stats["min"] == 5000
        assert stats["max"] == 5000

    def test_multiple_listings(self, config):
        analyzer = PriceAnalyzer(config)
        listings = [
            _make_listing(price_usd=5000),
            _make_listing(price_usd=7000),
            _make_listing(price_usd=9000),
        ]
        analyzer.add_listings(listings)
        stats = analyzer.get_stats()
        assert stats["count"] == 3
        assert stats["min"] == 5000
        assert stats["max"] == 9000
        assert stats["median"] == 7000


# ── Deal scoring ────────────────────────────────────────────────────


class TestDealScoring:
    """analyze() assigns deal scores to listings."""

    def test_scores_single_listing(self, config):
        analyzer = PriceAnalyzer(config)
        listing = _make_listing(price_usd=7500)
        analyzer.analyze([listing])
        assert listing.deal_score is not None
        assert 0 <= listing.deal_score <= 100

    def test_great_deal_flagged(self, config):
        analyzer = PriceAnalyzer(config)
        listing = _make_listing(price_usd=5000)
        analyzer.analyze([listing])
        assert listing.is_great_deal is True

    def test_expensive_not_great_deal(self, config):
        analyzer = PriceAnalyzer(config)
        listing = _make_listing(price_usd=12000)
        analyzer.analyze([listing])
        assert listing.is_great_deal is False

    def test_cheaper_gets_higher_score(self, config):
        analyzer = PriceAnalyzer(config)
        cheap = _make_listing(price_usd=4000)
        expensive = _make_listing(price_usd=10000)
        analyzer.analyze([cheap, expensive])
        assert cheap.deal_score > expensive.deal_score

    def test_listings_sorted_by_score(self, config):
        analyzer = PriceAnalyzer(config)
        listings = [
            _make_listing(price_usd=10000),
            _make_listing(price_usd=4000),
            _make_listing(price_usd=7000),
        ]
        result = analyzer.analyze(listings)
        scores = [listing.deal_score for listing in result]
        assert scores == sorted(scores, reverse=True)


# ── Top deals ───────────────────────────────────────────────────────


class TestTopDeals:
    """get_top_deals returns the best-scoring listings."""

    def test_returns_top_n(self, config):
        analyzer = PriceAnalyzer(config)
        listings = [_make_listing(price_usd=p) for p in [3000, 5000, 7000, 9000, 11000]]
        analyzer.analyze(listings)
        top = analyzer.get_top_deals(count=3)
        assert len(top) == 3

    def test_uses_config_count(self, config):
        analyzer = PriceAnalyzer(config)
        listings = [_make_listing(price_usd=p) for p in [3000, 5000, 7000]]
        analyzer.analyze(listings)
        top = analyzer.get_top_deals()
        assert len(top) == 3  # config.top_deals_count=5, but only 3 listings


# ── Suspicious price detection ──────────────────────────────────────


class TestSuspiciousPrice:
    """Listings way below median with "new" condition get flagged."""

    def test_not_suspicious_with_few_listings(self, config):
        analyzer = PriceAnalyzer(config)
        listing = _make_listing(price_usd=1000, condition="new")
        analyzer.analyze([listing])
        # Only 1 listing, needs min_sample=3
        assert listing.is_great_deal is True

    def test_suspicious_when_very_cheap_and_new(self, config):
        analyzer = PriceAnalyzer(config)
        listings = [
            _make_listing(price_usd=7000, condition="used"),
            _make_listing(price_usd=7500, condition="used"),
            _make_listing(price_usd=2000, condition="brand new"),
        ]
        analyzer.analyze(listings)
        cheap = listings[2]
        # Should be capped at 10.0 and not marked great deal
        assert cheap.deal_score <= 10.0
        assert cheap.is_great_deal is False

    def test_not_suspicious_when_reasonably_priced(self, config):
        analyzer = PriceAnalyzer(config)
        listings = [
            _make_listing(price_usd=7000, condition="used"),
            _make_listing(price_usd=7500, condition="used"),
            _make_listing(price_usd=6500, condition="new"),
        ]
        analyzer.analyze(listings)
        assert listings[2].deal_score > 10.0


# ── Price drop detection ────────────────────────────────────────────


class TestPriceDrop:
    """is_meaningful_price_drop decides if a price change is worth alerting."""

    def test_detects_meaningful_drop(self, config):
        assert is_meaningful_price_drop(10000, 8000, config) is True

    def test_ignores_small_drop(self, config):
        assert is_meaningful_price_drop(10000, 9800, config) is False

    def test_ignores_price_increase(self, config):
        assert is_meaningful_price_drop(10000, 11000, config) is False

    def test_ignores_none_old_price(self, config):
        assert is_meaningful_price_drop(None, 8000, config) is False

    def test_disabled_in_config(self, config):
        config.price_drop.enabled = False
        assert is_meaningful_price_drop(10000, 5000, config) is False

    def test_usd_threshold(self, config):
        config.price_drop.min_drop_usd = 500
        # $400 drop (< $500 min)
        assert is_meaningful_price_drop(10000, 9600, config) is False
        # $600 drop (>= $500 min)
        assert is_meaningful_price_drop(10000, 9400, config) is True


# ── Score breakdown formatting ──────────────────────────────────────


class TestFormatScoreBreakdown:
    """format_score_breakdown renders breakdown dict as a string."""

    def test_empty_breakdown(self):
        assert format_score_breakdown(None) == ""
        assert format_score_breakdown({}) == ""

    def test_formats_components(self):
        breakdown = {"base": 50, "price_vs_median": 10.5, "condition": 3.0}
        result = format_score_breakdown(breakdown)
        assert "base 50" in result
        assert "price +10.5" in result
        assert "condition +3.0" in result

    def test_negative_values(self):
        breakdown = {"price_vs_median": -5.2}
        result = format_score_breakdown(breakdown)
        assert "price -5.2" in result
