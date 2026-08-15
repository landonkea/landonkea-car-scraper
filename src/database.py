# ───────────────────────────────────────────────────────────────────
# Database models, SQLAlchemy ORM
# ───────────────────────────────────────────────────────────────────
# Defines the SQLite schema for car listings. Each row is one
# listing found on a marketplace. Car-specific columns (year, make,
# model, mileage, transmission, doors, title_status, fuel_type) are
# parsed from listing titles and stored for filtering/scoring.
# ───────────────────────────────────────────────────────────────────

import os
from datetime import datetime, timedelta, timezone
from typing import Optional  # noqa: F401 -- used in type comments

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Boolean,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class Listing(Base):
    """A single listing scraped from a marketplace."""
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Source identification ───────────────────────────────────
    source = Column(String(50), nullable=False, index=True)
    listing_id = Column(String(200), nullable=False)

    # ── Listing details ─────────────────────────────────────────
    title = Column(String(500), nullable=False)
    price_usd = Column(Float, nullable=False, index=True)
    currency = Column(String(3), default="USD")
    url = Column(Text, nullable=False)
    condition = Column(String(50), nullable=True)
    location = Column(String(200), nullable=True)

    # ── Car-specific fields ─────────────────────────────────────
    year = Column(Integer, nullable=True)
    make = Column(String(50), nullable=True)
    model = Column(String(50), nullable=True)
    mileage = Column(Integer, nullable=True)
    transmission = Column(String(20), nullable=True)
    doors = Column(Integer, nullable=True)
    title_status = Column(String(20), nullable=True)
    fuel_type = Column(String(20), nullable=True)

    # ── Deal scoring ────────────────────────────────────────────
    deal_score = Column(Float, nullable=True)
    is_great_deal = Column(Boolean, default=False)

    # ── Runtime-only scoring attributes (NOT database columns) ──
    deal_score_breakdown = None  # type: Optional[dict]
    car_kbb_price = None  # type: Optional[float]
    vs_kbb_pct = None  # type: Optional[float]

    # ── Timestamps ──────────────────────────────────────────────
    first_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("source", "listing_id", name="uq_source_listing"),
    )

    def __repr__(self) -> str:
        return (
            f"<Listing(id={self.id}, source='{self.source}', "
            f"${self.price_usd:.0f}, {self.year} {self.make} {self.model}, "
            f"deal_score={self.deal_score})>"
        )


class DailyPriceStat(Base):
    """Daily min/avg/max price per car model, for trend charts."""
    __tablename__ = "daily_price_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, index=True)
    product_name = Column(String(100), nullable=False)
    group_key = Column(String(50), nullable=False, index=True)
    min_price = Column(Float, nullable=False)
    avg_price = Column(Float, nullable=False)
    max_price = Column(Float, nullable=False)
    listing_count = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("date", "group_key", name="uq_date_group_key"),
    )

    def __repr__(self) -> str:
        return (
            f"<DailyPriceStat(date='{self.date}', group='{self.group_key}', "
            f"min=${self.min_price:.0f}, avg=${self.avg_price:.0f}, "
            f"max=${self.max_price:.0f}, n={self.listing_count})>"
        )


class PriceHistory(Base):
    """One price observation for one listing, at a point in time."""
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    listing_id = Column(Integer, nullable=False, index=True)
    price_usd = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self) -> str:
        return (
            f"<PriceHistory(listing_id={self.listing_id}, "
            f"price=${self.price_usd:.0f}, recorded_at={self.recorded_at})>"
        )


def record_price_history(db, listing: Listing, price_usd: float) -> bool:
    """
    Append a PriceHistory row if the price is new or has changed.
    Returns True if a new row was added.
    """
    last = (
        db.query(PriceHistory)
        .filter(PriceHistory.listing_id == listing.id)
        .order_by(PriceHistory.recorded_at.desc())
        .first()
    )
    if last is not None and last.price_usd == price_usd:
        return False

    db.add(PriceHistory(listing_id=listing.id, price_usd=price_usd))
    return True


def get_engine(database_url: str):
    """Create a database engine (the connection to SQLite)."""
    engine = create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    return engine


def create_tables(engine):
    """Create all tables that don't exist yet. Idempotent."""
    Base.metadata.create_all(engine)


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_migrations(database_url: str) -> None:
    """Bring the database up to the latest Alembic migration."""
    cfg = AlembicConfig(os.path.join(_PROJECT_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_PROJECT_ROOT, "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


RETENTION_DAYS = 180


def prune_old_inactive_listings(db, days: int = RETENTION_DAYS) -> int:
    """Permanently delete listings inactive for more than `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stale_ids = [
        row.id
        for row in db.query(Listing.id)
        .filter(Listing.is_active == False, Listing.last_seen_at < cutoff)
        .all()
    ]

    if not stale_ids:
        return 0

    db.query(PriceHistory).filter(PriceHistory.listing_id.in_(stale_ids)).delete(
        synchronize_session=False
    )
    deleted = (
        db.query(Listing)
        .filter(Listing.id.in_(stale_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def get_session(database_url: str) -> Session:
    """Get a database session for reading/writing."""
    engine = get_engine(database_url)
    run_migrations(database_url)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
