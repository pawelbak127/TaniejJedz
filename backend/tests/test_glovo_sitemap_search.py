"""
Tests for modified GlovoAdapter — sitemap-based search.

Run: pytest tests/test_glovo_sitemap_search.py -v

These tests verify:
  1. search_restaurants reads slugs from Redis (sitemap path)
  2. Falls back to HTML scraping when Redis is empty
  3. Non-food filtering works on sitemap slugs
  4. _slug_to_name produces readable names
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.scraper.adapters.glovo import GlovoAdapter
from app.scraper.schemas.normalized import NormalizedRestaurant


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def mock_redis():
    """Mock Redis with get/set/setex support."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    return redis


@pytest_asyncio.fixture
async def adapter(mock_redis):
    """GlovoAdapter with mocked Redis."""
    a = GlovoAdapter(mock_redis)
    # Patch infrastructure to avoid real connections
    a._cb = AsyncMock()
    a._cb.check = AsyncMock()
    a._budget = AsyncMock()
    a._budget.acquire = AsyncMock()
    a._proxy = MagicMock()
    a._proxy.get_proxy = MagicMock(return_value=None)
    a._settings = MagicMock()
    a._settings.scraper_timeout_realtime = 8.0
    return a


# ═══════════════════════════════════════════════════════════════
# Sitemap-based search
# ═══════════════════════════════════════════════════════════════

class TestSitemapSearch:

    @pytest.mark.asyncio
    async def test_reads_slugs_from_redis(self, adapter, mock_redis):
        """When Redis has sitemap slugs, should use them directly."""
        slugs = ["kfc-waw", "pizza-hut-waw", "burger-king-waw"]
        # First call: response cache miss
        # Second call: sitemap slugs hit
        mock_redis.get = AsyncMock(side_effect=[
            None,  # cache miss
            json.dumps(slugs),  # sitemap slugs
        ])

        results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        assert len(results) == 3
        assert all(isinstance(r, NormalizedRestaurant) for r in results)
        assert results[0].platform == "glovo"
        assert results[0].platform_slug == "kfc-waw"

    @pytest.mark.asyncio
    async def test_filters_non_food_from_sitemap(self, adapter, mock_redis):
        """Non-food slugs should be filtered even from sitemap data."""
        slugs = ["kfc-waw", "biedronka-express-mokotow", "rossmann-centrum", "pizza-hut-waw"]
        mock_redis.get = AsyncMock(side_effect=[
            None,  # cache miss
            json.dumps(slugs),  # sitemap slugs with non-food
        ])

        results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        result_slugs = [r.platform_slug for r in results]
        assert "kfc-waw" in result_slugs
        assert "pizza-hut-waw" in result_slugs
        assert "biedronka-express-mokotow" not in result_slugs
        assert "rossmann-centrum" not in result_slugs

    @pytest.mark.asyncio
    async def test_no_http_requests_for_sitemap_search(self, adapter, mock_redis):
        """Sitemap-based search should NOT make any HTTP requests."""
        slugs = ["kfc-waw"]
        mock_redis.get = AsyncMock(side_effect=[
            None,
            json.dumps(slugs),
        ])

        # Patch _get to detect if any HTTP call is made
        adapter._get = AsyncMock()

        results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        assert len(results) == 1
        adapter._get.assert_not_called()

    @pytest.mark.asyncio
    async def test_correct_platform_url(self, adapter, mock_redis):
        """Platform URL should use the resolved city_slug."""
        slugs = ["kfc-waw"]
        mock_redis.get = AsyncMock(side_effect=[None, json.dumps(slugs)])

        results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        assert "glovoapp.com/pl/pl/warszawa/stores/kfc-waw" in results[0].platform_url

    @pytest.mark.asyncio
    async def test_krakow_city_resolution(self, adapter, mock_redis):
        """Kraków coordinates should resolve to krakow city_slug."""
        slugs = ["kfc-kra"]
        # Need separate redis key for krakow
        mock_redis.get = AsyncMock(side_effect=[None, json.dumps(slugs)])

        results = await adapter.search_restaurants(50.06, 19.94, 5.0)

        assert "glovoapp.com/pl/pl/krakow/stores/kfc-kra" in results[0].platform_url


# ═══════════════════════════════════════════════════════════════
# Fallback to HTML scraping
# ═══════════════════════════════════════════════════════════════

class TestFallbackSearch:

    @pytest.mark.asyncio
    async def test_fallback_when_redis_empty(self, adapter, mock_redis):
        """Should fall back to HTML scraping when no sitemap slugs in Redis."""
        mock_redis.get = AsyncMock(return_value=None)  # Always None

        # Mock HTML scraping
        mock_html_result = [NormalizedRestaurant(
            platform="glovo",
            platform_restaurant_id="test-slug",
            platform_name="Test Restaurant",
            platform_slug="test-slug",
            platform_url="https://glovoapp.com/pl/pl/warszawa/stores/test-slug",
            name="Test Restaurant",
            latitude=0.0,
            longitude=0.0,
            is_online=True,
        )]

        with patch.object(adapter, '_scrape_category_page', new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = mock_html_result
            results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        assert len(results) == 1
        mock_scrape.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_response_cache(self, adapter, mock_redis):
        """Should return cached response without checking sitemap slugs."""
        cached_data = [NormalizedRestaurant(
            platform="glovo",
            platform_restaurant_id="cached-slug",
            platform_name="Cached",
            platform_slug="cached-slug",
            platform_url="https://glovoapp.com/pl/pl/warszawa/stores/cached-slug",
            name="Cached",
            latitude=0.0,
            longitude=0.0,
            is_online=True,
        ).model_dump(mode="json")]

        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        assert len(results) == 1
        assert results[0].platform_slug == "cached-slug"
        # Only 1 Redis call (cache check) — no sitemap slug check needed
        assert mock_redis.get.call_count == 1


# ═══════════════════════════════════════════════════════════════
# Slug to name conversion
# ═══════════════════════════════════════════════════════════════

class TestSlugToName:
    def test_basic(self):
        assert GlovoAdapter._slug_to_name("kfc-waw") == "Kfc"

    def test_multi_word(self):
        assert GlovoAdapter._slug_to_name("pizza-hut-kra") == "Pizza Hut"

    def test_no_city_suffix(self):
        assert GlovoAdapter._slug_to_name("dominos-pizza-warszawa-mokotow") == "Dominos Pizza Warszawa Mokotow"

    def test_trailing_number(self):
        assert GlovoAdapter._slug_to_name("burger-king2-waw") == "Burger King"

    def test_short_slug(self):
        assert GlovoAdapter._slug_to_name("kfc") == "Kfc"


# ═══════════════════════════════════════════════════════════════
# Non-food filtering (expanded list)
# ═══════════════════════════════════════════════════════════════

class TestNonFoodFiltering:
    def test_new_non_food_entries(self):
        """Verify newly added non-food keywords."""
        assert GlovoAdapter._is_non_food_slug("dino-market-waw")
        assert GlovoAdapter._is_non_food_slug("intermarche-express")
        assert GlovoAdapter._is_non_food_slug("netto-krakow")
        assert GlovoAdapter._is_non_food_slug("pepco-galeria")
        assert GlovoAdapter._is_non_food_slug("decathlon-waw")

    def test_food_restaurants_pass(self):
        assert not GlovoAdapter._is_non_food_slug("da-grasso-waw")
        assert not GlovoAdapter._is_non_food_slug("sushi-master-kra")
        assert not GlovoAdapter._is_non_food_slug("telepizza-wro")
