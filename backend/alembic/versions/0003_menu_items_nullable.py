"""platform_menu_items: nullable canonical_menu_item_id

Revision ID: 0003_menu_items_nullable
Revises: 0002_platform_rest_geo
Create Date: 2026-03-17

Changes:
- Change canonical_menu_item_id from NOT NULL to nullable
  (platform menu items can exist before menu matching assigns canonical)
- Add partial index idx_platform_menu_items_unmatched
  (fast lookup of unmatched items for menu matcher)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_menu_items_nullable"
down_revision: Union[str, None] = "0002_platform_rest_geo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Make canonical_menu_item_id nullable ─────────────────
    op.alter_column(
        "platform_menu_items",
        "canonical_menu_item_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=True,
    )

    # ── Partial index for unmatched menu items ──────────────
    op.execute("""
        CREATE INDEX idx_platform_menu_items_unmatched
        ON platform_menu_items (platform_restaurant_id, canonical_menu_item_id)
        WHERE canonical_menu_item_id IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_platform_menu_items_unmatched")

    op.alter_column(
        "platform_menu_items",
        "canonical_menu_item_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=False,
    )
