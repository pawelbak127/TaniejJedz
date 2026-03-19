"""
TaniejJedz Scraper Engine — Epic 3.

Submodules:
  proxy_manager    — Bright Data residential proxy rotation
  fingerprint      — User-Agent pool, header building, human-like delays
  budget_manager   — Daily request caps per platform, Redis counters, alerts
  session_manager  — Per-session cookie jars persisted in Redis
  circuit_breaker  — Per-platform circuit breaker (fail-fast on outages)
  orchestrator     — Parallel multi-platform fetch with cache fallback
  quality_scorer   — Score scrape results for data quality
"""

from app.scraper.proxy_manager import ProxyManager
from app.scraper.fingerprint import build_headers, human_delay, get_random_ua
from app.scraper.budget_manager import BudgetManager, BudgetExhaustedError
from app.scraper.session_manager import SessionManager
from app.scraper.circuit_breaker import CircuitBreaker, CircuitOpenError

__all__ = [
    "ProxyManager",
    "build_headers",
    "human_delay",
    "get_random_ua",
    "BudgetManager",
    "BudgetExhaustedError",
    "SessionManager",
    "CircuitBreaker",
    "CircuitOpenError",
]
