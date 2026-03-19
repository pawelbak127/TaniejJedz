"""
Platform adapters — one module per delivery platform.

Sprint 3.2: app/scraper/adapters/wolt.py    ✅
Sprint 3.3: app/scraper/adapters/pyszne.py  ✅
"""

from app.scraper.adapters.wolt import WoltAdapter
from app.scraper.adapters.pyszne import PyszneAdapter

__all__ = ["WoltAdapter", "PyszneAdapter"]
