"""Add seller_type, vin columns to listings.

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("seller_type", sa.String(20), nullable=True))
    op.add_column("listings", sa.Column("vin", sa.String(17), nullable=True))
    op.create_index("ix_listings_vin", "listings", ["vin"])


def downgrade() -> None:
    op.drop_index("ix_listings_vin", "listings")
    op.drop_column("listings", "vin")
    op.drop_column("listings", "seller_type")
