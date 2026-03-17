"""Admin API: scraper health dashboard — read-only."""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.dependencies import DbSession

router = APIRouter(prefix="/api/admin/scrapers", tags=["admin-scrapers"])


class ScraperHealthEntry(BaseModel):
    platform: str
    city_slug: str
    success: bool
    response_time_ms: int | None = None
    data_quality_score: float | None = None
    checked_at: str


class ScraperHealthResponse(BaseModel):
    entries: list[ScraperHealthEntry]
    total: int


class ScraperHealthSummary(BaseModel):
    platform: str
    city_slug: str
    total_checks: int
    success_count: int
    success_rate: float
    avg_response_ms: float | None = None
    avg_quality: float | None = None


class ScraperSummaryResponse(BaseModel):
    summaries: list[ScraperHealthSummary]


@router.get("/health", response_model=ScraperHealthResponse)
async def list_scraper_health(
    db: DbSession,
    platform: str | None = Query(default=None),
    city_slug: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> ScraperHealthResponse:
    """List recent scraper health entries."""
    conditions = []
    params: dict = {"limit": limit}

    if platform:
        conditions.append("platform = :platform")
        params["platform"] = platform
    if city_slug:
        conditions.append("city_slug = :city_slug")
        params["city_slug"] = city_slug

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = text(f"""
        SELECT platform, city_slug, success, response_time_ms,
               data_quality_score, checked_at
        FROM scraper_health
        {where_clause}
        ORDER BY checked_at DESC
        LIMIT :limit
    """)

    result = await db.execute(query, params)
    rows = result.fetchall()

    entries = [
        ScraperHealthEntry(
            platform=r.platform,
            city_slug=r.city_slug,
            success=r.success,
            response_time_ms=r.response_time_ms,
            data_quality_score=r.data_quality_score,
            checked_at=r.checked_at.isoformat(),
        )
        for r in rows
    ]

    return ScraperHealthResponse(entries=entries, total=len(entries))


@router.get("/summary", response_model=ScraperSummaryResponse)
async def scraper_health_summary(
    db: DbSession,
    hours: int = Query(default=24, ge=1, le=168),
) -> ScraperSummaryResponse:
    """Aggregated scraper health summary per platform/city."""
    query = text("""
        SELECT platform, city_slug,
               COUNT(*) as total_checks,
               SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
               AVG(response_time_ms) as avg_response_ms,
               AVG(data_quality_score) as avg_quality
        FROM scraper_health
        WHERE checked_at > now() - make_interval(hours => :hours)
        GROUP BY platform, city_slug
        ORDER BY platform, city_slug
    """)

    result = await db.execute(query, {"hours": hours})
    rows = result.fetchall()

    summaries = [
        ScraperHealthSummary(
            platform=r.platform,
            city_slug=r.city_slug,
            total_checks=r.total_checks,
            success_count=r.success_count,
            success_rate=r.success_count / r.total_checks if r.total_checks > 0 else 0.0,
            avg_response_ms=round(r.avg_response_ms, 1) if r.avg_response_ms else None,
            avg_quality=round(r.avg_quality, 3) if r.avg_quality else None,
        )
        for r in rows
    ]

    return ScraperSummaryResponse(summaries=summaries)
