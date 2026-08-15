"""Baseline schema for car scraper.

Revision ID: 0001
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("listing_id", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("price_usd", sa.Float, nullable=True),
        sa.Column("currency", sa.String(3), default="USD"),
        sa.Column("url", sa.String, nullable=True),
        sa.Column("condition", sa.String, nullable=True),
        sa.Column("location", sa.String, nullable=True),
        # Car-specific fields
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("make", sa.String, nullable=True),
        sa.Column("model", sa.String, nullable=True),
        sa.Column("mileage", sa.Integer, nullable=True),
        sa.Column("transmission", sa.String, nullable=True),
        sa.Column("doors", sa.Integer, nullable=True),
        sa.Column("title_status", sa.String, nullable=True),
        sa.Column("fuel_type", sa.String, nullable=True),
        # Electronics fields (kept for compatibility with apple scraper code)
        sa.Column("storage_capacity_gb", sa.Float, nullable=True),
        sa.Column("generation", sa.String, nullable=True),
        sa.Column("chipset", sa.String, nullable=True),
        sa.Column("ram_gb", sa.Float, nullable=True),
        sa.Column("has cellular", sa.Boolean, nullable=True),
        # Deal tracking
        sa.Column("is_great_deal", sa.Boolean, default=False),
        sa.Column("deal_score", sa.Float, nullable=True),
        sa.Column("score_breakdown", sa.String, nullable=True),
        # Lifecycle tracking
        sa.Column("first_seen_at", sa.DateTime, nullable=True),
        sa.Column("last_seen_at", sa.DateTime, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        # Search config snapshot
        sa.Column("search_product_type", sa.String, nullable=True),
        sa.Column("search_min_price", sa.Float, nullable=True),
        sa.Column("search_max_price", sa.Float, nullable=True),
        sa.Column("search_preferred_sellers", sa.String, nullable=True),
        sa.Column("search_regions", sa.String, nullable=True),
        sa.Column("search_platforms", sa.String, nullable=True),
        sa.Column("search_local_only", sa.Boolean, nullable=True),
        sa.Column("search_min_year", sa.Integer, nullable=True),
        sa.Column("search_max_mileage", sa.Integer, nullable=True),
        sa.Column("search_transmission", sa.String, nullable=True),
        sa.Column("search_min_doors", sa.Integer, nullable=True),
        sa.Column("search_title_status", sa.String, nullable=True),
        sa.Column("search_fuel_type", sa.String, nullable=True),
    )

    # SQLite doesn't support named unique constraints in the same way
    # The constraint is created via the UniqueConstraint in the table definition

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("listing_id", sa.Integer, nullable=False),
        sa.Column("price_usd", sa.Float, nullable=False),
        sa.Column("recorded_at", sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"],
            name="fk_price_history_listing_id",
        ),
    )

    op.create_table(
        "daily_price_stats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("date", sa.String, nullable=False),
        sa.Column("product_name", sa.String, nullable=False),
        sa.Column("group_key", sa.String, nullable=False),
        # Summary stats
        sa.Column("min_price", sa.Float, nullable=False),
        sa.Column("avg_price", sa.Float, nullable=False),
        sa.Column("max_price", sa.Float, nullable=False),
        sa.Column("listing_count", sa.Integer, nullable=False),
        # Timestamps
        sa.Column("updated_at", sa.DateTime, nullable=False),
        # Unique constraint on date + group_key
        sa.UniqueConstraint("date", "group_key",
                          name="uq_date_group_key"),
    )


def downgrade() -> None:
    op.drop_table("daily_price_stats")
    op.drop_table("price_history")
    op.drop_table("listings")
