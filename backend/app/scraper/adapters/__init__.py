"""
Platform adapters — one module per delivery platform.

Sprint 3.2: app/scraper/adapters/wolt.py    ✅
Sprint 3.3: app/scraper/adapters/pyszne.py  ✅
Sprint 3.6: app/scraper/adapters/glovo.py   ✅
Sprint 3.7: app/scraper/adapters/ubereats.py ✅
"""

from app.scraper.adapters.wolt import WoltAdapter
from app.scraper.adapters.pyszne import PyszneAdapter
from app.scraper.adapters.glovo import GlovoAdapter
from app.scraper.adapters.ubereats import UberEatsAdapter

__all__ = ["WoltAdapter", "PyszneAdapter", "GlovoAdapter", "UberEatsAdapter"]
