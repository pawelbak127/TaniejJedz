"""
Manual test — real Glovo API.
Usage:
  cd backend
  $env:REDIS_URL="redis://:localdevpassword@localhost:6379/0"
  python -m app.scraper.tests.manual_test_glovo
"""

import asyncio
import sys

from redis.asyncio import Redis
from app.config import get_settings
from app.scraper.adapters.glovo import GlovoAdapter
from app.scraper.budget_manager import BudgetManager
from app.scraper.circuit_breaker import CircuitBreaker


async def main() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    adapter = GlovoAdapter(redis)

    # Test with known slug
    slug = "kfc-waw"
    print("=" * 60)
    print(f"GLOVO: store detail + menu for {slug}")
    print("=" * 60)

    # 1. Store detail
    print("\n--- Store Detail ---")
    try:
        store = await adapter._get_store_detail(slug)
        print(f"  Name: {store.name}")
        print(f"  ID: {store.id}, AddressID: {store.addressId}")
        print(f"  Open: {store.is_online}")
        print(f"  Delivery fee: {store.delivery_fee_grosz / 100:.2f} zł")
        print(f"  Service fee: {store.service_fee_grosz / 100:.2f} zł")
        print(f"  Cuisines: {store.cuisine_tags}")
    except Exception as exc:
        print(f"  ✗ Store detail failed: {exc}")
        await redis.aclose()
        sys.exit(1)

    # 2. Menu
    print("\n--- Menu ---")
    try:
        items = await adapter.get_menu(slug)
        print(f"  Items: {len(items)}")

        cats: dict[str, list] = {}
        for item in items:
            cats.setdefault(item.category_name, []).append(item)

        for cat_name, cat_items in list(cats.items())[:6]:
            print(f"\n  [{cat_name}]")
            for item in cat_items[:4]:
                avail = "✓" if item.is_available else "✗"
                mods = f" ({len(item.modifier_groups)} mod)" if item.modifier_groups else ""
                print(f"    {avail} {item.platform_name}: {item.price_grosz / 100:.2f} zł{mods}")
            if len(cat_items) > 4:
                print(f"    ... +{len(cat_items) - 4}")

        # Show modifiers
        item_with_mods = next((i for i in items if i.modifier_groups), None)
        if item_with_mods:
            print(f"\n--- Modyfikatory: {item_with_mods.platform_name} ---")
            for mg in item_with_mods.modifier_groups[:3]:
                req = "WYMAGANY" if mg.group_type == "required" else "opcjonalny"
                print(f"  {mg.name} [{req}] (min={mg.min_selections}, max={mg.max_selections})")
                for opt in mg.options[:5]:
                    d = " ★" if opt.is_default else ""
                    print(f"    - {opt.name}: +{opt.price_grosz / 100:.2f} zł{d}")
                if len(mg.options) > 5:
                    print(f"    ... +{len(mg.options) - 5}")

    except Exception as exc:
        print(f"  ✗ Menu failed: {exc}")

    # 3. Quality check
    if items:
        from app.scraper.quality_scorer import score_menu
        report = score_menu(items, "glovo", slug)
        print(f"\n--- Quality ---")
        print(f"  Score: {report.score:.3f} [{report.status.upper()}]")

    # 4. Infra
    print(f"\n{'=' * 60}")
    print("INFRASTRUKTURA")
    print("=" * 60)
    bm = BudgetManager(redis)
    s = await bm.get_status("glovo")
    print(f"  Budget:  {s['used']}/{s['cap']} ({s['pct_used'] * 100:.1f}%)")
    cb = CircuitBreaker(redis)
    info = await cb.get_info("glovo")
    print(f"  Circuit: {info['state']} (failures={info['failures']})")

    print("\n✓ Done!")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
