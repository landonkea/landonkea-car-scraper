"""Tests for car product type handler.

Covers title parsing, relevance filtering, type filters, and deal scoring.
"""
import pytest
from unittest.mock import MagicMock

from product_types.cars import CarHandler, MINIMUM_PRICE_USD


@pytest.fixture
def handler():
    return CarHandler()


@pytest.fixture
def mock_search():
    """A minimal search config for testing filters."""
    search = MagicMock()
    search.min_year = 2015
    search.max_mileage = 150000
    search.transmission = "automatic"
    search.min_doors = 4
    search.title_status = "clean"
    search.preferred_brands = ["Honda", "Toyota"]
    return search


@pytest.fixture
def mock_listing():
    """A minimal listing object for testing scoring/filters."""
    listing = MagicMock()
    listing.year = 2018
    listing.make = "Honda"
    listing.model = "Fit"
    listing.mileage = 60000
    listing.transmission = "Automatic"
    listing.doors = 4
    listing.title_status = "Clean"
    listing.fuel_type = "Gas"
    listing.price_usd = 7500
    return listing


# ── parse_specs ─────────────────────────────────────────────────────


class TestParseSpecs:
    """parse_specs extracts car details from listing titles."""

    def test_extracts_year(self, handler):
        specs = handler.parse_specs("2018 Honda Fit LX")
        assert specs["year"] == 2018

    def test_extracts_make(self, handler):
        specs = handler.parse_specs("2018 Honda Fit LX")
        assert specs["make"] == "Honda"

    def test_extracts_model(self, handler):
        specs = handler.parse_specs("2018 Honda Civic LX")
        assert "civic" in specs["model"].lower()

    def test_extracts_mileage_with_k_suffix(self, handler):
        specs = handler.parse_specs("2018 Honda Fit, 60k miles")
        assert specs["mileage"] == 60000

    def test_extracts_mileage_with_commas(self, handler):
        specs = handler.parse_specs("2018 Honda Fit, 125,000 miles")
        assert specs["mileage"] == 125000

    def test_extracts_transmission_automatic(self, handler):
        specs = handler.parse_specs("2018 Honda Fit Automatic")
        assert specs["transmission"] == "Automatic"

    def test_extracts_transmission_manual(self, handler):
        specs = handler.parse_specs("2018 Honda Fit Manual")
        assert specs["transmission"] == "Manual"

    def test_extracts_transmission_cvt(self, handler):
        specs = handler.parse_specs("2018 Honda Fit CVT")
        assert specs["transmission"] == "CVT"

    def test_extracts_doors_from_keyword(self, handler):
        specs = handler.parse_specs("2018 Honda Fit 4 door")
        assert specs["doors"] == 4

    def test_extracts_doors_from_sedan(self, handler):
        specs = handler.parse_specs("2018 Honda Fit Sedan")
        assert specs["doors"] == 4

    def test_extracts_doors_from_hatchback(self, handler):
        specs = handler.parse_specs("2018 Honda Fit Hatchback")
        assert specs["doors"] == 4

    def test_extracts_title_status_clean(self, handler):
        specs = handler.parse_specs("2018 Honda Fit, clean title")
        assert specs["title_status"] == "Clean"

    def test_extracts_title_status_salvage(self, handler):
        specs = handler.parse_specs("2018 Honda Fit, salvage title")
        assert specs["title_status"] == "Salvage"

    def test_extracts_title_status_rebuilt(self, handler):
        specs = handler.parse_specs("2018 Honda Fit, rebuilt title")
        assert specs["title_status"] == "Rebuilt"

    def test_extracts_fuel_type_hybrid(self, handler):
        specs = handler.parse_specs("2018 Honda Fit Hybrid")
        assert specs["fuel_type"] == "Hybrid"

    def test_extracts_fuel_type_electric(self, handler):
        specs = handler.parse_specs("2018 Honda Fit Electric")
        assert specs["fuel_type"] == "Electric"

    def test_extracts_fuel_type_diesel(self, handler):
        specs = handler.parse_specs("2018 Honda Fit Diesel")
        assert specs["fuel_type"] == "Diesel"

    def test_returns_none_for_unknown_make(self, handler):
        specs = handler.parse_specs("2018 Zamboni XL")
        assert specs["make"] is None

    def test_returns_none_for_no_year(self, handler):
        specs = handler.parse_specs("Honda Fit, good condition")
        assert specs["year"] is None

    def test_returns_none_for_no_mileage(self, handler):
        specs = handler.parse_specs("2018 Honda Fit")
        assert specs["mileage"] is None

    def test_sets_electronics_fields_to_none(self, handler):
        specs = handler.parse_specs("2018 Honda Fit")
        assert specs["ram_gb"] is None
        assert specs["storage_gb"] is None
        assert specs["chip"] is None


# ── is_relevant ─────────────────────────────────────────────────────


class TestIsRelevant:
    """is_relevant filters out parts, accessories, and broken cars."""

    def test_rejects_parts_only(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit - parts only", mock_search) is False

    def test_rejects_parting_out(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit - parting out", mock_search) is False

    def test_rejects_engine_only(self, handler, mock_search):
        assert handler.is_relevant("Honda Fit engine only", mock_search) is False

    def test_rejects_does_not_run(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit - does not run", mock_search) is False

    def test_rejects_no_engine(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit, no engine", mock_search) is False

    def test_rejects_blown_motor(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit, blown motor", mock_search) is False

    def test_rejects_flood_damage(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit, flood damage", mock_search) is False

    def test_rejects_frame_damage(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit, frame damage", mock_search) is False

    def test_rejects_salvage_title(self, handler, mock_search):
        # salvage title is filtered in both is_relevant and passes_type_filters
        assert handler.is_relevant("2018 Honda Fit, salvage title", mock_search) is False

    def test_rejects_floor_mats_only(self, handler, mock_search):
        assert handler.is_relevant("Honda Fit floor mats", mock_search) is False

    def test_accepts_clean_listing(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit LX - Clean, runs great", mock_search) is True

    def test_accepts_listing_with_condition_field(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit", mock_search, condition="parts only") is False

    def test_accepts_normal_condition(self, handler, mock_search):
        assert handler.is_relevant("2018 Honda Fit", mock_search, condition="excellent") is True


# ── passes_type_filters ─────────────────────────────────────────────


class TestPassesTypeFilters:
    """passes_type_filters enforces year, mileage, transmission, doors, title."""

    def test_passes_with_valid_listing(self, handler, mock_listing, mock_search):
        assert handler.passes_type_filters(mock_listing, mock_search) is True

    def test_rejects_too_old(self, handler, mock_listing, mock_search):
        mock_listing.year = 2012
        assert handler.passes_type_filters(mock_listing, mock_search) is False

    def test_rejects_too_many_miles(self, handler, mock_listing, mock_search):
        mock_listing.mileage = 200000
        assert handler.passes_type_filters(mock_listing, mock_search) is False

    def test_rejects_wrong_transmission(self, handler, mock_listing, mock_search):
        mock_listing.transmission = "Manual"
        assert handler.passes_type_filters(mock_listing, mock_search) is False

    def test_rejects_too_few_doors(self, handler, mock_listing, mock_search):
        mock_listing.doors = 2
        assert handler.passes_type_filters(mock_listing, mock_search) is False

    def test_rejects_salvage_title(self, handler, mock_listing, mock_search):
        mock_listing.title_status = "Salvage"
        assert handler.passes_type_filters(mock_listing, mock_search) is False

    def test_passes_with_none_year(self, handler, mock_listing, mock_search):
        mock_listing.year = None
        assert handler.passes_type_filters(mock_listing, mock_search) is True

    def test_passes_with_none_mileage(self, handler, mock_listing, mock_search):
        mock_listing.mileage = None
        assert handler.passes_type_filters(mock_listing, mock_search) is True

    def test_passes_with_any_transmission(self, handler, mock_listing, mock_search):
        mock_search.transmission = "Any"
        mock_listing.transmission = "Manual"
        assert handler.passes_type_filters(mock_listing, mock_search) is True

    def test_passes_with_any_title_status(self, handler, mock_listing, mock_search):
        mock_search.title_status = "Any"
        mock_listing.title_status = "Salvage"
        assert handler.passes_type_filters(mock_listing, mock_search) is True


# ── score_bonuses ───────────────────────────────────────────────────


class TestScoreBonuses:
    """score_bonuses awards points for desirable car attributes."""

    def test_clean_title_bonus(self, handler, mock_listing, mock_search):
        mock_listing.title_status = "Clean"
        score = handler.score_bonuses(mock_listing, mock_search)
        assert score >= 15

    def test_low_mileage_bonus(self, handler, mock_listing, mock_search):
        mock_listing.mileage = 30000
        score = handler.score_bonuses(mock_listing, mock_search)
        assert score >= 15

    def test_medium_mileage_bonus(self, handler, mock_listing, mock_search):
        mock_listing.mileage = 70000
        score = handler.score_bonuses(mock_listing, mock_search)
        assert score >= 10

    def test_high_mileage_bonus(self, handler, mock_listing, mock_search):
        mock_listing.mileage = 90000
        score = handler.score_bonuses(mock_listing, mock_search)
        assert score >= 5

    def test_newer_year_bonus(self, handler, mock_listing, mock_search):
        mock_listing.year = 2022
        score = handler.score_bonuses(mock_listing, mock_search)
        assert score >= 10

    def test_reliable_make_bonus(self, handler, mock_listing, mock_search):
        mock_listing.make = "Toyota"
        score = handler.score_bonuses(mock_listing, mock_search)
        assert score >= 5

    def test_hybrid_bonus(self, handler, mock_listing, mock_search):
        mock_listing.fuel_type = "Hybrid"
        score = handler.score_bonuses(mock_listing, mock_search)
        assert score >= 3

    def test_max_possible_score(self, handler, mock_search):
        """Best possible car: clean title, low miles, 2022+, Honda, hybrid."""
        listing = MagicMock()
        listing.title_status = "Clean"
        listing.mileage = 20000
        listing.year = 2022
        listing.make = "Honda"
        listing.fuel_type = "Hybrid"
        score = handler.score_bonuses(listing, mock_search)
        # 15 (clean) + 15 (low miles) + 10 (new year) + 5 (reliable) + 3 (hybrid) = 48
        assert score == 48

    def test_zero_bonus_for_bad_listing(self, handler, mock_search):
        listing = MagicMock()
        listing.title_status = "Salvage"
        listing.mileage = 200000
        listing.year = 2010
        listing.make = "Ferrari"
        listing.fuel_type = "Gas"
        score = handler.score_bonuses(listing, mock_search)
        assert score == 0


# ── min_price_usd ───────────────────────────────────────────────────


class TestMinPrice:
    """min_price_usd returns the floor price to exclude parts cars."""

    def test_returns_500(self, handler, mock_search):
        assert handler.min_price_usd(mock_search) == MINIMUM_PRICE_USD

    def test_is_500(self):
        assert MINIMUM_PRICE_USD == 500
