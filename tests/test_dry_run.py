"""Tests for dry run mode.

Verifies the full pipeline works end-to-end without sending alerts.
"""
import pytest
from unittest.mock import MagicMock, patch

from config import load_config, Config
from scrapers.base import ScrapedListing
from price_analyzer import PriceAnalyzer
from database import Listing, get_session


@pytest.fixture
def config_file(tmp_path):
    """Write a minimal config for dry run testing."""
    import yaml
    cfg = {
        "environment": "dev",
        "request_timeout": 40,
        "database": {"url": f"sqlite:///{tmp_path}/test.db"},
        "searches": [
            {
                "product_name": "Honda Fit (2015+, automatic)",
                "product_type": "car",
                "min_year": 2015,
                "max_mileage": 150000,
                "transmission": "automatic",
                "min_doors": 4,
                "title_status": "clean",
                "preferred_brands": ["Honda"],
                "min_price": 500,
            }
        ],
        "price": {
            "absolute_max_usd": 15000,
            "great_deal_usd": {"car": 6000},
            "good_deal_usd": {"car": 8000},
            "top_deals_count": 5,
        },
        "alerts": {
            "email": {"enabled": False, "smtp_server": "", "smtp_port": 587},
            "discord": {"enabled": True},
        },
        "sites": {
            "craigslist": {"enabled": False},
            "offerup": {"enabled": False},
            "ebay": {"enabled": False},
            "cargurus": {"enabled": False},
            "autotrader": {"enabled": False},
            "facebook": {"enabled": False},
        },
        "schedule": {"enabled": True, "interval_hours": 6},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg))
    return str(path)


@pytest.fixture
def sample_listings():
    """A handful of sample ScrapedListings for testing the pipeline."""
    return [
        ScrapedListing(
            source="craigslist",
            listing_id="cl-001",
            title="2018 Honda Fit LX",
            price_usd=5500,
            url="https://example.com/001",
            condition=None,
            location="Phoenix",
            year=2018,
            make="Honda",
            model="Fit",
            mileage=45000,
            transmission="Automatic",
            doors=4,
            title_status="Clean",
            fuel_type=None,
        ),
        ScrapedListing(
            source="craigslist",
            listing_id="cl-002",
            title="2020 Nissan Versa S",
            price_usd=7500,
            url="https://example.com/002",
            condition=None,
            location="Tucson",
            year=2020,
            make="Nissan",
            model="Versa",
            mileage=30000,
            transmission="Automatic",
            doors=4,
            title_status="Clean",
            fuel_type=None,
        ),
        ScrapedListing(
            source="offerup",
            listing_id="ou-001",
            title="2016 Chevy Spark LT",
            price_usd=4200,
            url="https://example.com/003",
            condition=None,
            location="Phoenix",
            year=2016,
            make="Chevrolet",
            model="Spark",
            mileage=80000,
            transmission="Automatic",
            doors=4,
            title_status="Clean",
            fuel_type=None,
        ),
    ]


# ── Config loading ──────────────────────────────────────────────────


class TestDryRunConfig:
    """Config loads correctly for dry run."""

    def test_loads_config(self, config_file):
        config = load_config(config_file)
        assert config is not None
        assert config.environment in ("dev", "production")

    def test_has_searches(self, config_file):
        config = load_config(config_file)
        assert len(config.searches) == 1
        assert config.searches[0].product_type == "car"


# ── Price analyzer pipeline ─────────────────────────────────────────


class TestDryRunPipeline:
    """Price analyzer processes listings and scores them."""

    def test_analyzer_scores_listings(self, config_file, sample_listings):
        config = load_config(config_file)
        config.search = config.searches[0]

        analyzer = PriceAnalyzer(config)
        result = analyzer.analyze(sample_listings)

        assert len(result) == 3
        for listing in result:
            assert listing.deal_score is not None
            assert 0 <= listing.deal_score <= 100

    def test_great_deal_flagged(self, config_file, sample_listings):
        config = load_config(config_file)
        config.search = config.searches[0]

        analyzer = PriceAnalyzer(config)
        result = analyzer.analyze(sample_listings)

        great_deals = [l for l in result if l.is_great_deal]
        assert len(great_deals) >= 1

    def test_top_deals_returned(self, config_file, sample_listings):
        config = load_config(config_file)
        config.search = config.searches[0]

        analyzer = PriceAnalyzer(config)
        analyzer.analyze(sample_listings)
        top = analyzer.get_top_deals(count=2)

        assert len(top) == 2
        assert top[0].deal_score >= top[1].deal_score

    def test_stats_computed(self, config_file, sample_listings):
        config = load_config(config_file)
        config.search = config.searches[0]

        analyzer = PriceAnalyzer(config)
        analyzer.analyze(sample_listings)
        stats = analyzer.get_stats()

        assert stats["count"] == 3
        assert stats["min"] == 4200
        assert stats["max"] == 7500


# ── Database integration ────────────────────────────────────────────


class TestDryRunDatabase:
    """Listings can be saved to the database in dry run mode."""

    def test_saves_listings_to_db(self, config_file, sample_listings):
        config = load_config(config_file)
        db = get_session(config.database.url)

        for sl in sample_listings:
            listing = Listing(
                source=sl.source,
                listing_id=sl.listing_id,
                title=sl.title,
                price_usd=sl.price_usd,
                url=sl.url,
                condition=sl.condition,
                location=sl.location,
                year=sl.year,
                make=sl.make,
                model=sl.model,
                mileage=sl.mileage,
                transmission=sl.transmission,
                doors=sl.doors,
                title_status=sl.title_status,
                fuel_type=sl.fuel_type,
            )
            db.add(listing)
        db.commit()

        count = db.query(Listing).count()
        assert count == 3
        db.close()

    def test_upsert_works(self, config_file, sample_listings):
        config = load_config(config_file)
        db = get_session(config.database.url)

        # Add first listing
        sl = sample_listings[0]
        listing = Listing(
            source=sl.source,
            listing_id=sl.listing_id,
            title=sl.title,
            price_usd=sl.price_usd,
            url=sl.url,
            year=sl.year,
            make=sl.make,
            model=sl.model,
            mileage=sl.mileage,
        )
        db.add(listing)
        db.commit()

        # Update same listing
        listing.price_usd = 5000
        db.commit()

        count = db.query(Listing).count()
        assert count == 1
        assert db.query(Listing).first().price_usd == 5000
        db.close()


# ── Scraper registry ────────────────────────────────────────────────


class TestScraperRegistry:
    """SCRAPER_CLASSES maps source names to scraper classes."""

    def test_all_sources_registered(self):
        from main import SCRAPER_CLASSES
        expected = ["craigslist", "offerup", "ebay", "cargurus", "autotrader", "facebook"]
        for source in expected:
            assert source in SCRAPER_CLASSES

    def test_classes_have_scrape_method(self):
        from main import SCRAPER_CLASSES
        for cls in SCRAPER_CLASSES.values():
            assert hasattr(cls, "scrape")
