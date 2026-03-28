"""platform_restaurants: add lat/lng, nullable canonical_restaurant_id

Revision ID: 0002_platform_rest_geo
Revises: 0001_initial
Create Date: 2026-03-17

Changes:
- Add latitude, longitude columns to platform_restaurants (for PostGIS blocking in matcher)
- Change canonical_restaurant_id from NOT NULL to nullable (platform restaurant can exist before entity matching)
- Add partial index idx_platform_rest_geo (WHERE lat/lng NOT NULL)
- Add partial index idx_platform_rest_unmatched (WHERE canonical_restaurant_id IS NULL)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_platform_rest_geo"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Add latitude, longitude columns ─────────────────────
    op.add_column(
        "platform_restaurants",
        sa.Column("latitude", sa.Float, nullable=True),
    )
    op.add_column(
        "platform_restaurants",
        sa.Column("longitude", sa.Float, nullable=True),
    )

    # ── Make canonical_restaurant_id nullable ────────────────
    # Flow: scrape → persist (canonical_id=NULL) → match → UPDATE SET canonical_restaurant_id
    op.alter_column(
        "platform_restaurants",
        "canonical_restaurant_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=True,
    )

    # ── Partial index for geospatial blocking (matcher) ─────
    op.execute("""
        CREATE INDEX idx_platform_rest_geo
        ON platform_restaurants (latitude, longitude)
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)

    # ── Partial index for unmatched restaurants (matcher) ────
    op.execute("""
        CREATE INDEX idx_platform_rest_unmatched
        ON platform_restaurants (platform, canonical_restaurant_id)
        WHERE canonical_restaurant_id IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_platform_rest_unmatched")
    op.execute("DROP INDEX IF EXISTS idx_platform_rest_geo")

    # Restore NOT NULL (will fail if any NULLs exist)
    op.alter_column(
        "platform_restaurants",
        "canonical_restaurant_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=False,
    )

    op.drop_column("platform_restaurants", "longitude")
    op.drop_column("platform_restaurants", "latitude")
