"""POST /api/v1/search — address-based restaurant search."""

import uuid as _uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, and_
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession
from app.models.city import City
from app.models.restaurant import CanonicalRestaurant, PlatformRestaurant, OperatingHours
from app.models.delivery import DeliveryFee
from app.schemas.search import (
    DataFreshnessInfo,
    PlatformAvailability,
    RestaurantSummary,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search_restaurants(body: SearchRequest, db: DbSession) -> SearchResponse:
    """Search restaurants by address/coordinates with filters and pagination."""

    # ── Find city ───────────────────────────────────────────
    city_stmt = select(City).where(City.is_active.is_(True)).limit(1)
    city_result = await db.execute(city_stmt)
    city = city_result.scalar_one_or_none()
    city_name = city.name if city else "Warszawa"
    city_id = city.id if city else None

    # ── Base query: active restaurants in city ──────────────
    stmt = (
        select(CanonicalRestaurant)
        .where(
            CanonicalRestaurant.is_active.is_(True),
        )
        .options(
            selectinload(CanonicalRestaurant.platform_restaurants)
            .selectinload(PlatformRestaurant.operating_hours),
            selectinload(CanonicalRestaurant.platform_restaurants)
            .selectinload(PlatformRestaurant.delivery_fees),
        )
    )

    if city_id:
        stmt = stmt.where(CanonicalRestaurant.city_id == city_id)

    # ── Cuisine filter ──────────────────────────────────────
    if body.cuisine_filter:
        stmt = stmt.where(
            CanonicalRestaurant.cuisine_tags.overlap(body.cuisine_filter)
        )

    # ── Count total before pagination ───────────────────────
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # ── Sorting ─────────────────────────────────────────────
    if body.sort_by == "rating":
        stmt = stmt.order_by(CanonicalRestaurant.data_quality_score.desc())
    elif body.sort_by == "cheapest_delivery":
        stmt = stmt.order_by(CanonicalRestaurant.name.asc())
    else:
        stmt = stmt.order_by(CanonicalRestaurant.data_quality_score.desc())

    # ── Pagination ──────────────────────────────────────────
    offset = (body.page - 1) * body.per_page
    stmt = stmt.offset(offset).limit(body.per_page)

    result = await db.execute(stmt)
    restaurants = result.scalars().unique().all()

    # ── Build response ──────────────────────────────────────
    summaries: list[RestaurantSummary] = []
    for r in restaurants:
        platforms: dict[str, PlatformAvailability] = {}
        cheapest_fee: int | None = None
        cheapest_platform: str | None = None

        for pr in r.platform_restaurants:
            if not pr.is_active:
                continue

            fee_grosz: int | None = None
            estimated_min: int | None = None
            if pr.delivery_fees:
                latest_fee = pr.delivery_fees[0]
                fee_grosz = latest_fee.fee_grosz
                estimated_min = latest_fee.estimated_minutes

            is_open = True  # default open; real check comes in later sprints

            platforms[pr.platform] = PlatformAvailability(
                available=True,
                is_open=is_open,
                rating=None,
                delivery_minutes=estimated_min,
                delivery_fee_grosz=fee_grosz,
            )

            if is_open and fee_grosz is not None:
                if cheapest_fee is None or fee_grosz < cheapest_fee:
                    cheapest_fee = fee_grosz
                    cheapest_platform = pr.platform

        address_str = r.address_street or ""
        if r.address_city:
            address_str = f"{address_str}, {r.address_city}" if address_str else r.address_city

        summaries.append(
            RestaurantSummary(
                id=str(r.id),
                name=r.name,
                address=address_str,
                latitude=r.latitude,
                longitude=r.longitude,
                cuisine_tags=list(r.cuisine_tags) if r.cuisine_tags else [],
                image_url=r.image_url,
                data_quality_score=r.data_quality_score,
                platforms=platforms,
                cheapest_open_platform=cheapest_platform,
                cheapest_delivery_fee_grosz=cheapest_fee,
            )
        )

    return SearchResponse(
        restaurants=summaries,
        total=total,
        page=body.page,
        per_page=body.per_page,
        city=city_name,
        data_freshness={},
    )
