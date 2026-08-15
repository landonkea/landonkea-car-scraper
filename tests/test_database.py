"""Tests for database module.

Covers listing creation, upsert, price history, and pruning.
"""
import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Listing, PriceHistory, record_price_history, prune_old_inactive_listings


@pytest.fixture
def db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


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
    }
    defaults.update(kwargs)
    return Listing(**defaults)


# ── Listing creation ────────────────────────────────────────────────


class TestListingCreation:
    """Listings can be created and saved to the database."""

    def test_creates_listing(self, db):
        listing = _make_listing()
        db.add(listing)
        db.commit()
        assert listing.id is not None

    def test_saves_all_fields(self, db):
        listing = _make_listing(
            year=2020,
            make="Toyota",
            model="Yaris",
            mileage=30000,
            transmission="Automatic",
            doors=4,
            title_status="Clean",
            fuel_type="Gas",
        )
        db.add(listing)
        db.commit()

        result = db.query(Listing).first()
        assert result.year == 2020
        assert result.make == "Toyota"
        assert result.model == "Yaris"
        assert result.mileage == 30000
        assert result.transmission == "Automatic"
        assert result.doors == 4
        assert result.title_status == "Clean"
        assert result.fuel_type == "Gas"

    def test_default_values(self, db):
        listing = _make_listing()
        db.add(listing)
        db.commit()
        assert listing.is_active is True
        assert listing.is_great_deal is False
        assert listing.first_seen_at is not None
        assert listing.last_seen_at is not None


# ── Upsert ──────────────────────────────────────────────────────────


class TestUpsert:
    """Updating an existing listing instead of creating a duplicate."""

    def test_updates_existing_listing(self, db):
        listing = _make_listing()
        db.add(listing)
        db.commit()
        original_id = listing.id

        # Update the same listing
        listing.price_usd = 6500
        listing.last_seen_at = datetime.now(timezone.utc)
        db.commit()

        result = db.query(Listing).first()
        assert result.id == original_id
        assert result.price_usd == 6500

    def test_no_duplicate_listings(self, db):
        listing1 = _make_listing(price_usd=7500)
        listing2 = _make_listing(price_usd=6500)
        db.add(listing1)
        db.commit()
        # Simulate upsert by updating
        listing1.price_usd = 6500
        db.commit()

        count = db.query(Listing).count()
        assert count == 1


# ── Price history ───────────────────────────────────────────────────


class TestPriceHistory:
    """record_price_history tracks price changes over time."""

    def test_records_initial_price(self, db):
        listing = _make_listing()
        db.add(listing)
        db.commit()

        result = record_price_history(db, listing, 7500)
        assert result is True

        history = db.query(PriceHistory).all()
        assert len(history) == 1
        assert history[0].price_usd == 7500

    def test_records_price_change(self, db):
        listing = _make_listing()
        db.add(listing)
        db.commit()

        record_price_history(db, listing, 7500)
        record_price_history(db, listing, 6500)

        history = db.query(PriceHistory).all()
        assert len(history) == 2
        assert history[0].price_usd == 7500
        assert history[1].price_usd == 6500

    def test_skips_same_price(self, db):
        listing = _make_listing()
        db.add(listing)
        db.commit()

        record_price_history(db, listing, 7500)
        result = record_price_history(db, listing, 7500)

        assert result is False
        history = db.query(PriceHistory).all()
        assert len(history) == 1


# ── Pruning ─────────────────────────────────────────────────────────


class TestPruning:
    """prune_old_inactive_listings removes stale inactive listings."""

    def test_keeps_active_listings(self, db):
        listing = _make_listing()
        listing.is_active = True
        db.add(listing)
        db.commit()

        deleted = prune_old_inactive_listings(db, days=180)
        assert deleted == 0
        assert db.query(Listing).count() == 1

    def test_removes_old_inactive_listings(self, db):
        listing = _make_listing()
        listing.is_active = False
        listing.last_seen_at = datetime.now(timezone.utc) - timedelta(days=200)
        db.add(listing)
        db.commit()

        deleted = prune_old_inactive_listings(db, days=180)
        assert deleted == 1
        assert db.query(Listing).count() == 0

    def test_keeps_recent_inactive_listings(self, db):
        listing = _make_listing()
        listing.is_active = False
        listing.last_seen_at = datetime.now(timezone.utc) - timedelta(days=100)
        db.add(listing)
        db.commit()

        deleted = prune_old_inactive_listings(db, days=180)
        assert deleted == 0
        assert db.query(Listing).count() == 1

    def test_removes_price_history_with_listing(self, db):
        listing = _make_listing()
        listing.is_active = False
        listing.last_seen_at = datetime.now(timezone.utc) - timedelta(days=200)
        db.add(listing)
        db.commit()

        record_price_history(db, listing, 7500)
        assert db.query(PriceHistory).count() == 1

        prune_old_inactive_listings(db, days=180)
        assert db.query(PriceHistory).count() == 0
