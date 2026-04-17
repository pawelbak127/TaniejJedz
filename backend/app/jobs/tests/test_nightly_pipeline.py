"""
Tests for jobs.nightly_pipeline — Sprint 4.6.

Structural tests verifying pipeline steps, ordering, and stats.
"""

from __future__ import annotations

import os
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.jobs.nightly_pipeline import (
    ALL_STEPS,
    PipelineStats,
    run_pipeline,
    nightly_pipeline,
)


@pytest.fixture(autouse=True)
def _clear_settings():
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ══════════════════════════════════════════════════════════════
# PipelineStats
# ══════════════════════════════════════════════════════════════


class TestPipelineStats:

    def test_initial_defaults(self):
        s = PipelineStats()
        assert s.city == ""
        assert s.crawl_restaurants == {}
        assert s.restaurant_match_auto == 0
        assert s.menus_crawled == 0
        assert s.menu_match_auto == 0

    def test_to_dict(self):
        s = PipelineStats(city="warszawa", elapsed_s=120.5)
        s.crawl_restaurants = {"wolt": 1378, "pyszne": 578}
        s.restaurant_match_auto = 287
        d = s.to_dict()
        assert d["city"] == "warszawa"
        assert d["elapsed_s"] == 120.5
        assert d["crawl"]["wolt"] == 1378
        assert d["restaurant_matching"]["auto"] == 287

    def test_errors_tracked(self):
        s = PipelineStats()
        s.step_errors["crawl"] = "connection refused"
        d = s.to_dict()
        assert "crawl" in d["errors"]


# ══════════════════════════════════════════════════════════════
# PIPELINE STRUCTURE
# ══════════════════════════════════════════════════════════════


class TestPipelineStructure:

    def test_all_steps_defined(self):
        assert ALL_STEPS == [
            "crawl", "match_restaurants", "crawl_menus", "match_menus"
        ]

    def test_step_order_correct(self):
        """Steps must run in dependency order."""
        assert ALL_STEPS.index("crawl") < ALL_STEPS.index("match_restaurants")
        assert ALL_STEPS.index("match_restaurants") < ALL_STEPS.index("crawl_menus")
        assert ALL_STEPS.index("crawl_menus") < ALL_STEPS.index("match_menus")

    def test_run_pipeline_is_async(self):
        import inspect
        assert inspect.iscoroutinefunction(run_pipeline)

    def test_dramatiq_actor_exists(self):
        assert hasattr(nightly_pipeline, "send")

    def test_pipeline_uses_restaurant_matcher(self):
        import inspect
        from app.jobs.nightly_pipeline import _step_match_restaurants
        source = inspect.getsource(_step_match_restaurants)
        assert "RestaurantMatcher" in source
        assert "match_all_platforms" in source

    def test_pipeline_uses_menu_matcher(self):
        import inspect
        from app.jobs.nightly_pipeline import _step_match_menus
        source = inspect.getsource(_step_match_menus)
        assert "MenuMatcher" in source
        assert "match_all" in source

    def test_pipeline_crawls_cross_platform_menus(self):
        """Menu crawl step must target cross-platform restaurants."""
        import inspect
        from app.jobs.nightly_pipeline import _step_crawl_menus
        source = inspect.getsource(_step_crawl_menus)
        assert "COUNT(DISTINCT platform) >= 2" in source

    def test_pipeline_logs_to_redis(self):
        import inspect
        from app.jobs.nightly_pipeline import _log_pipeline_result
        source = inspect.getsource(_log_pipeline_result)
        assert "pipeline:last_run" in source
        assert "pipeline:history" in source

    def test_pipeline_handles_step_errors(self):
        """Pipeline must continue on step failure."""
        import inspect
        from app.jobs.nightly_pipeline import run_pipeline
        source = inspect.getsource(run_pipeline)
        assert "step_errors" in source
        assert "except Exception" in source

    def test_cli_entrypoint(self):
        """Pipeline must be runnable as __main__."""
        import inspect
        import app.jobs.nightly_pipeline as mod
        source = inspect.getsource(mod)
        assert 'if __name__ == "__main__"' in source
        assert "argparse" in source

    def test_selective_steps_supported(self):
        """Pipeline must support running subset of steps."""
        import inspect
        source = inspect.getsource(run_pipeline)
        assert "run_steps" in source
