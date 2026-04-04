"""
Tests for UberEats sitemap sync + modified adapter.

Run: pytest tests/test_ubereats_sitemap.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.jobs.sync_ubereats_slugs import (
    _extract_stores_from_xml,
    _is_non_food_slug,
)
from app.scraper.adapters.ubereats import UberEatsAdapter
from app.scraper.schemas.normalized import NormalizedRestaurant


# ═══════════════════════════════════════════════════════════════
# sync_ubereats_slugs — XML extraction
# ═══════════════════════════════════════════════════════════════

class TestExtractStores:
    def _make_sitemap(self, urls: list[str]) -> str:
        locs = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
        return f'<?xml version="1.0"?>\n<urlset>{locs}\n</urlset>'

    def test_basic_extraction(self):
        xml = self._make_sitemap([
            "https://www.ubereats.com/pl/store/kfc-mokotow/Kiwgl6M6SsKGc8WCuaxtNA",
            "https://www.ubereats.com/pl-en/store/pizza-hut/xRmQDC50UxO5OWpRW-v5ZQ",
        ])
        stores = _extract_stores_from_xml(xml)
        assert len(stores) == 2
        assert stores[0]["slug"] == "kfc-mokotow"
        assert stores[0]["uuid"] == "Kiwgl6M6SsKGc8WCuaxtNA"
        assert stores[0]["locale"] == "pl"
        assert stores[1]["locale"] == "pl-en"

    def test_url_encoded_slug(self):
        xml = self._make_sitemap([
            "https://www.ubereats.com/pl/store/pizza-na-cienkim-w%C5%82osku/r3WQRuN4UkunOgosRHxY0A",
        ])
        stores = _extract_stores_from_xml(xml)
        assert len(stores) == 1
        assert "włosku" in stores[0]["slug"]  # URL-decoded

    def test_non_polish_urls_ignored(self):
        xml = self._make_sitemap([
            "https://www.ubereats.com/de/store/pizza-berlin/abc123",
            "https://www.ubereats.com/pl/store/pizza-waw/def456",
            "https://www.ubereats.com/us/store/pizza-nyc/ghi789",
        ])
        stores = _extract_stores_from_xml(xml)
        assert len(stores) == 1
        assert stores[0]["slug"] == "pizza-waw"

    def test_empty_sitemap(self):
        xml = '<?xml version="1.0"?>\n<urlset></urlset>'
        stores = _extract_stores_from_xml(xml)
        assert stores == []

    def test_base64_uuid_with_special_chars(self):
        """UberEats uses URL-safe base64: A-Z, a-z, 0-9, -, _."""
        xml = self._make_sitemap([
            "https://www.ubereats.com/pl/store/test/TE8bFy87XtGAs11jlNIDYQ",
            "https://www.ubereats.com/pl/store/test2/_WeHJovQRQWPNagXtKV9cg",
            "https://www.ubereats.com/pl/store/test3/2OfXT7x5UrK_5GhbVMIW-g",
        ])
        stores = _extract_stores_from_xml(xml)
        assert len(stores) == 3
        assert stores[2]["uuid"] == "2OfXT7x5UrK_5GhbVMIW-g"


class TestNonFoodFilter:
    def test_food_passes(self):
        assert not _is_non_food_slug("kfc-mokotow")
        assert not _is_non_food_slug("pizza-hut-warszawa")

    def test_non_food_blocked(self):
        assert _is_non_food_slug("biedronka-express")
        assert _is_non_food_slug("rossmann-centrum")
        assert _is_non_food_slug("apteka-zdrowia")


# ═══════════════════════════════════════════════════════════════
# UberEatsAdapter — sitemap-based search
# ═══════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    return redis


@pytest_asyncio.fixture
async def adapter(mock_redis):
    a = UberEatsAdapter(mock_redis)
    a._cb = AsyncMock()
    a._cb.check = AsyncMock()
    a._budget = AsyncMock()
    a._budget.acquire = AsyncMock()
    a._proxy = MagicMock()
    a._proxy.get_proxy = MagicMock(return_value=None)
    a._settings = MagicMock()
    a._settings.scraper_timeout_realtime = 8.0
    return a


class TestSitemapSearch:

    @pytest.mark.asyncio
    async def test_reads_stores_from_redis(self, adapter, mock_redis):
        stores = [
            {"slug": "kfc-mokotow", "uuid": "abc123", "locale": "pl"},
            {"slug": "pizza-hut", "uuid": "def456", "locale": "pl-en"},
        ]
        mock_redis.get = AsyncMock(side_effect=[
            None,  # cache miss
            json.dumps(stores),  # sitemap stores
        ])

        results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        assert len(results) == 2
        assert all(r.platform == "ubereats" for r in results)
        # Critical: platform_slug must be UUID
        assert results[0].platform_slug == "abc123"
        assert results[1].platform_slug == "def456"

    @pytest.mark.asyncio
    async def test_no_http_for_sitemap(self, adapter, mock_redis):
        stores = [{"slug": "test", "uuid": "xyz789", "locale": "pl"}]
        mock_redis.get = AsyncMock(side_effect=[None, json.dumps(stores)])

        adapter._post = AsyncMock()
        results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        assert len(results) == 1
        adapter._post.assert_not_called()

    @pytest.mark.asyncio
    async def test_platform_url_format(self, adapter, mock_redis):
        stores = [{"slug": "kfc-mokotow", "uuid": "abc123", "locale": "pl-en"}]
        mock_redis.get = AsyncMock(side_effect=[None, json.dumps(stores)])

        results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        assert "ubereats.com/pl-en/store/kfc-mokotow/abc123" in results[0].platform_url

    @pytest.mark.asyncio
    async def test_fallback_when_redis_empty(self, adapter, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(adapter, '_batch_suggestions', new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = {}
            results = await adapter.search_restaurants(52.23, 21.01, 5.0)

        mock_batch.assert_called_once()


class TestSlugToName:
    def test_basic(self):
        assert UberEatsAdapter._slug_to_name("kfc-mokotow") == "Kfc Mokotow"

    def test_ampersand(self):
        assert UberEatsAdapter._slug_to_name("hot-rolls-&-kebab") == "Hot Rolls & Kebab"

    def test_url_decoded(self):
        assert UberEatsAdapter._slug_to_name("pizza-na-cienkim-włosku") == "Pizza Na Cienkim Włosku"
