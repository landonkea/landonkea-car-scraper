"""Tests for config loading and car-specific fields.

Uses a minimal config fixture to test parsing without real API keys.
"""
import pytest
import yaml

from config import load_config


MINIMAL_CONFIG = {
    "environment": "dev",
    "request_timeout": 40,
    "database": {"url": "sqlite:///data/test.db"},
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
        "top_deals_count": 10,
    },
    "alerts": {
        "email": {"enabled": False, "smtp_server": "", "smtp_port": 587},
        "discord": {"enabled": True},
    },
    "sites": {
        "craigslist": {"enabled": True, "applicable_product_types": ["car"]},
        "offerup": {"enabled": True},
        "ebay": {"enabled": True},
        "cargurus": {"enabled": True},
        "autotrader": {"enabled": True},
        "facebook": {"enabled": False},
    },
    "schedule": {"enabled": True, "interval_hours": 6},
}


@pytest.fixture
def config_file(tmp_path):
    """Write a minimal config to a temp file and return its path."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(MINIMAL_CONFIG))
    return str(path)


class TestConfigLoading:
    """Config loader reads YAML and returns typed objects."""

    def test_loads_config_from_file(self, config_file):
        config = load_config(config_file)
        assert config is not None
        assert config.environment in ("dev", "production")

    def test_loads_searches(self, config_file):
        config = load_config(config_file)
        assert len(config.searches) == 1

    def test_loads_database_url(self, config_file):
        config = load_config(config_file)
        assert "test.db" in config.database.url

    def test_loads_price_thresholds(self, config_file):
        config = load_config(config_file)
        assert config.price.great_deal_usd["car"] == 6000
        assert config.price.good_deal_usd["car"] == 8000

    def test_loads_site_enabled_states(self, config_file):
        config = load_config(config_file)
        assert config.sites.craigslist.enabled is True
        assert config.sites.facebook.enabled is False


class TestSearchConfig:
    """SearchConfig holds car-specific search parameters."""

    def test_has_product_name(self, config_file):
        config = load_config(config_file)
        search = config.searches[0]
        assert search.product_name == "Honda Fit (2015+, automatic)"

    def test_has_product_type(self, config_file):
        config = load_config(config_file)
        search = config.searches[0]
        assert search.product_type == "car"

    def test_has_min_year(self, config_file):
        config = load_config(config_file)
        search = config.searches[0]
        assert search.min_year == 2015

    def test_has_max_mileage(self, config_file):
        config = load_config(config_file)
        search = config.searches[0]
        assert search.max_mileage == 150000

    def test_has_transmission(self, config_file):
        config = load_config(config_file)
        search = config.searches[0]
        assert search.transmission == "automatic"

    def test_has_min_doors(self, config_file):
        config = load_config(config_file)
        search = config.searches[0]
        assert search.min_doors == 4

    def test_has_title_status(self, config_file):
        config = load_config(config_file)
        search = config.searches[0]
        assert search.title_status == "clean"

    def test_has_preferred_brands(self, config_file):
        config = load_config(config_file)
        search = config.searches[0]
        assert "Honda" in search.preferred_brands


class TestPriceConfig:
    """PriceConfig defines deal thresholds."""

    def test_absolute_max_usd(self, config_file):
        config = load_config(config_file)
        assert config.price.absolute_max_usd == 15000

    def test_top_deals_count(self, config_file):
        config = load_config(config_file)
        assert config.price.top_deals_count == 10

    def test_suspicious_defaults(self, config_file):
        config = load_config(config_file)
        assert config.price.suspicious_price_ratio == 0.5
        assert config.price.suspicious_min_sample == 3


class TestSitesConfig:
    """SitesConfig holds per-site settings."""

    def test_craigslist_has_applicable_product_types(self, config_file):
        config = load_config(config_file)
        assert config.sites.craigslist.applicable_product_types == ["car"]

    def test_offerup_has_no_restrictions(self, config_file):
        config = load_config(config_file)
        assert config.sites.offerup.applicable_product_types is None


class TestMultipleSearches:
    """Config supports multiple product searches."""

    def test_loads_multiple_searches(self, tmp_path):
        cfg = dict(MINIMAL_CONFIG)
        cfg["searches"] = [
            {"product_name": "Honda Fit", "product_type": "car"},
            {"product_name": "Nissan Versa", "product_type": "car"},
        ]
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(cfg))
        config = load_config(str(path))
        assert len(config.searches) == 2

    def test_searches_independent(self, tmp_path):
        cfg = dict(MINIMAL_CONFIG)
        cfg["searches"] = [
            {"product_name": "Honda Fit", "min_year": 2015},
            {"product_name": "Nissan Versa", "min_year": 2018},
        ]
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(cfg))
        config = load_config(str(path))
        assert config.searches[0].min_year == 2015
        assert config.searches[1].min_year == 2018
