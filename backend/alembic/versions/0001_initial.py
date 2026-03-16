"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extensions ──────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "cube"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "earthdistance"')

    # ── cities ──────────────────────────────────────────────
    op.create_table(
        "cities",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("center_lat", sa.Float, nullable=False),
        sa.Column("center_lng", sa.Float, nullable=False),
        sa.Column("radius_km", sa.Integer, nullable=False, server_default="15"),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    # ── canonical_restaurants ───────────────────────────────
    op.create_table(
        "canonical_restaurants",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("city_id", UUID(as_uuid=True), sa.ForeignKey("cities.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("address_street", sa.String(255), nullable=True),
        sa.Column("address_city", sa.String(100), nullable=True),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("cuisine_tags", ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("chain_slug", sa.String(100), nullable=True),
        sa.Column("data_quality_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── platform_restaurants ────────────────────────────────
    op.create_table(
        "platform_restaurants",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("canonical_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("canonical_restaurants.id"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("platform_restaurant_id", sa.String(255), nullable=False),
        sa.Column("platform_name", sa.String(255), nullable=False),
        sa.Column("platform_slug", sa.String(255), nullable=True),
        sa.Column("platform_url", sa.String(512), nullable=True),
        sa.Column("match_confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("platform_metadata", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "platform_restaurant_id", name="uq_platform_rest_unique"),
    )

    # ── operating_hours ─────────────────────────────────────
    op.create_table(
        "operating_hours",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("platform_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("platform_restaurants.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=False),
        sa.Column("open_time", sa.Time, nullable=False),
        sa.Column("close_time", sa.Time, nullable=False),
        sa.Column("is_closed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── menu_categories ─────────────────────────────────────
    op.create_table(
        "menu_categories",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("canonical_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("canonical_restaurants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── canonical_menu_items ────────────────────────────────
    op.create_table(
        "canonical_menu_items",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("canonical_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("canonical_restaurants.id"), nullable=False),
        sa.Column("category_id", UUID(as_uuid=True), sa.ForeignKey("menu_categories.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("size_label", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── platform_menu_items ─────────────────────────────────
    op.create_table(
        "platform_menu_items",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("canonical_menu_item_id", UUID(as_uuid=True), sa.ForeignKey("canonical_menu_items.id"), nullable=False),
        sa.Column("platform_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("platform_restaurants.id"), nullable=False),
        sa.Column("platform_item_id", sa.String(255), nullable=False),
        sa.Column("platform_name", sa.String(255), nullable=False),
        sa.Column("price_grosz", sa.Integer, nullable=False),
        sa.Column("match_confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("is_available", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── canonical_modifier_groups (Phase 2, table created now) ──
    op.create_table(
        "canonical_modifier_groups",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("canonical_menu_item_id", UUID(as_uuid=True), sa.ForeignKey("canonical_menu_items.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("group_type", sa.String(20), nullable=False, server_default="optional"),
        sa.Column("min_selections", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_selections", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── canonical_modifier_options (Phase 2, table created now) ──
    op.create_table(
        "canonical_modifier_options",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("canonical_modifier_group_id", UUID(as_uuid=True), sa.ForeignKey("canonical_modifier_groups.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── modifier_groups ─────────────────────────────────────
    op.create_table(
        "modifier_groups",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("platform_menu_item_id", UUID(as_uuid=True), sa.ForeignKey("platform_menu_items.id"), nullable=False),
        sa.Column("canonical_modifier_group_id", UUID(as_uuid=True), sa.ForeignKey("canonical_modifier_groups.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("group_type", sa.String(20), nullable=False, server_default="optional"),
        sa.Column("min_selections", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_selections", sa.Integer, nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("platform_group_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── modifier_options ────────────────────────────────────
    op.create_table(
        "modifier_options",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("modifier_group_id", UUID(as_uuid=True), sa.ForeignKey("modifier_groups.id"), nullable=False),
        sa.Column("canonical_modifier_option_id", UUID(as_uuid=True), sa.ForeignKey("canonical_modifier_options.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("price_grosz", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_available", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("platform_option_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── delivery_fees ───────────────────────────────────────
    op.create_table(
        "delivery_fees",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("platform_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("platform_restaurants.id"), nullable=False),
        sa.Column("geohash", sa.String(12), nullable=True),
        sa.Column("fee_grosz", sa.Integer, nullable=False),
        sa.Column("min_order_grosz", sa.Integer, nullable=True),
        sa.Column("estimated_minutes", sa.Integer, nullable=True),
        sa.Column("free_delivery_above_grosz", sa.Integer, nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── promotions ──────────────────────────────────────────
    op.create_table(
        "promotions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("platform_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("platform_restaurants.id"), nullable=False),
        sa.Column("promo_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("discount_value", sa.Integer, nullable=False, server_default="0"),
        sa.Column("min_order_grosz", sa.Integer, nullable=True),
        sa.Column("subscription_only", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── user_feedback ───────────────────────────────────────
    op.create_table(
        "user_feedback",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("canonical_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("canonical_restaurants.id"), nullable=True),
        sa.Column("platform_menu_item_id", UUID(as_uuid=True), sa.ForeignKey("platform_menu_items.id"), nullable=True),
        sa.Column("feedback_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("city_slug", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("context_snapshot", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── entity_review_queue ─────────────────────────────────
    op.create_table(
        "entity_review_queue",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("platform_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("platform_restaurants.id"), nullable=False),
        sa.Column("candidate_canonical_id", UUID(as_uuid=True), sa.ForeignKey("canonical_restaurants.id"), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("match_details", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── comparison_logs ─────────────────────────────────────
    op.create_table(
        "comparison_logs",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("canonical_restaurant_id", UUID(as_uuid=True), sa.ForeignKey("canonical_restaurants.id"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("city_slug", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("platform_totals", JSONB, nullable=True),
        sa.Column("configured_items", JSONB, nullable=True),
        sa.Column("cheapest_platform", sa.String(50), nullable=True),
        sa.Column("savings_grosz", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── affiliate_clicks ────────────────────────────────────
    op.create_table(
        "affiliate_clicks",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("comparison_log_id", UUID(as_uuid=True), sa.ForeignKey("comparison_logs.id"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("handoff_method", sa.String(50), nullable=False, server_default="clipboard"),
        sa.Column("utm_params", JSONB, nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── feature_flags ───────────────────────────────────────
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("key"),
    )

    # ── PARTITIONED TABLES ──────────────────────────────────
    # SQLAlchemy's create_table doesn't natively support PARTITION BY,
    # so we use raw SQL for these three.

    # -- price_history (partitioned by month)
    op.execute("""
        CREATE TABLE price_history (
            id UUID NOT NULL DEFAULT uuid_generate_v4(),
            platform_menu_item_id UUID NOT NULL,
            price_grosz INTEGER NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, recorded_at)
        ) PARTITION BY RANGE (recorded_at)
    """)

    # -- analytics_events (partitioned by month)
    op.execute("""
        CREATE TABLE analytics_events (
            id UUID NOT NULL DEFAULT uuid_generate_v4(),
            event_type VARCHAR(100) NOT NULL,
            session_id VARCHAR(64) NOT NULL,
            payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    # -- scraper_health (partitioned by month)
    op.execute("""
        CREATE TABLE scraper_health (
            id UUID NOT NULL DEFAULT uuid_generate_v4(),
            platform VARCHAR(50) NOT NULL,
            city_slug VARCHAR(100) NOT NULL,
            success BOOLEAN NOT NULL,
            response_time_ms INTEGER,
            data_quality_score FLOAT,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, checked_at)
        ) PARTITION BY RANGE (checked_at)
    """)

    # ── Initial partitions (current + next 3 months) ────────
    _create_monthly_partitions("price_history", "recorded_at", 2026, [3, 4, 5, 6])
    _create_monthly_partitions("analytics_events", "created_at", 2026, [3, 4, 5, 6])
    _create_monthly_partitions("scraper_health", "checked_at", 2026, [3, 4, 5, 6])

    # ── INDEXES (from architecture 8.4) ─────────────────────

    # GiST index for geospatial queries (earthdistance)
    op.execute("""
        CREATE INDEX idx_restaurants_geo
        ON canonical_restaurants
        USING gist (ll_to_earth(latitude, longitude))
    """)

    # GIN trigram index for fuzzy name search
    op.execute("""
        CREATE INDEX idx_restaurants_name_trgm
        ON canonical_restaurants
        USING gin (normalized_name gin_trgm_ops)
    """)

    # Regular B-tree indexes
    op.create_index("idx_restaurants_city", "canonical_restaurants", ["city_id", "is_active"])
    op.execute("""
        CREATE INDEX idx_restaurants_chain
        ON canonical_restaurants (chain_slug)
        WHERE chain_slug IS NOT NULL
    """)

    op.create_index(
        "idx_platform_rest_canonical",
        "platform_restaurants",
        ["canonical_restaurant_id", "platform"],
    )

    op.create_index(
        "idx_menu_items_restaurant",
        "platform_menu_items",
        ["platform_restaurant_id", "is_available"],
    )
    op.create_index("idx_modifier_groups_item", "modifier_groups", ["platform_menu_item_id"])
    op.create_index("idx_modifier_options_group", "modifier_options", ["modifier_group_id"])

    op.create_index(
        "idx_hours_lookup",
        "operating_hours",
        ["platform_restaurant_id", "day_of_week"],
    )
    op.create_index(
        "idx_delfee_lookup",
        "delivery_fees",
        ["platform_restaurant_id", "geohash"],
    )

    op.execute("""
        CREATE INDEX idx_review_pending
        ON entity_review_queue (status, created_at)
        WHERE status = 'pending'
    """)
    op.execute("""
        CREATE INDEX idx_feedback_pending
        ON user_feedback (status, created_at)
        WHERE status = 'pending'
    """)
    op.execute("""
        CREATE INDEX idx_comparison_idempotency
        ON comparison_logs (idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX idx_price_history_item_date
        ON price_history (platform_menu_item_id, recorded_at DESC)
    """)


def downgrade() -> None:
    # Partitioned tables
    op.execute("DROP TABLE IF EXISTS price_history CASCADE")
    op.execute("DROP TABLE IF EXISTS analytics_events CASCADE")
    op.execute("DROP TABLE IF EXISTS scraper_health CASCADE")

    # Regular tables (reverse dependency order)
    op.drop_table("feature_flags")
    op.drop_table("affiliate_clicks")
    op.drop_table("comparison_logs")
    op.drop_table("entity_review_queue")
    op.drop_table("user_feedback")
    op.drop_table("promotions")
    op.drop_table("delivery_fees")
    op.drop_table("modifier_options")
    op.drop_table("modifier_groups")
    op.drop_table("canonical_modifier_options")
    op.drop_table("canonical_modifier_groups")
    op.drop_table("platform_menu_items")
    op.drop_table("canonical_menu_items")
    op.drop_table("menu_categories")
    op.drop_table("operating_hours")
    op.drop_table("platform_restaurants")
    op.drop_table("canonical_restaurants")
    op.drop_table("cities")


def _create_monthly_partitions(
    table: str, column: str, year: int, months: list[int]
) -> None:
    """Create monthly partition tables."""
    for month in months:
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year = year + 1
        partition_name = f"{table}_y{year}m{month:02d}"
        op.execute(f"""
            CREATE TABLE {partition_name} PARTITION OF {table}
            FOR VALUES FROM ('{year}-{month:02d}-01')
                        TO ('{next_year}-{next_month:02d}-01')
        """)
