"""Mock comparison worker — simulates platform scraping for SSE testing.

Each Dramatiq job:
1. Sleeps 1-3s (simulating httpx scrape).
2. HSET comparison:{id}:results {platform} → result JSON (BEFORE publish).
3. PUBLISH comparison:{id} → event JSON.
4. After all platforms → HSET _final, PUBLISH ready, EXPIRE 300s.

Replace with real scraper adapters in Epic 4.
"""

import json
import random
import time as _time

import dramatiq
from redis import Redis as SyncRedis

from app.config import get_settings

ENABLED_PLATFORMS = ["wolt", "pyszne"]
RESULTS_TTL_SECONDS = 300


def _get_sync_redis() -> SyncRedis:
    """Dramatiq actors are synchronous — use sync Redis client."""
    settings = get_settings()
    url = settings.redis_url
    return SyncRedis.from_url(url, decode_responses=True)


def _generate_mock_result(platform: str, request_json: str) -> dict:
    """Generate a fake platform comparison result."""
    # Parse request for item info
    try:
        request_data = json.loads(request_json)
        items = request_data.get("items", [])
    except (json.JSONDecodeError, KeyError):
        items = [{"canonical_item_id": "unknown", "quantity": 1}]

    base_price_offset = {"wolt": 0, "pyszne": -150}
    delivery_fees = {"wolt": 599, "pyszne": 499}
    delivery_minutes = {"wolt": 35, "pyszne": 40}

    comparison_items = []
    items_total = 0
    for item in items:
        # Random price between 2000-5000 grosz, offset per platform
        unit_price = random.randint(2000, 5000) + base_price_offset.get(platform, 0)
        qty = item.get("quantity", 1)
        item_total = unit_price * qty
        items_total += item_total

        comparison_items.append({
            "canonical_item_id": item.get("canonical_item_id", "unknown"),
            "name": f"Item {item.get('canonical_item_id', 'x')[:8]}",
            "quantity": qty,
            "unit_price_grosz": unit_price,
            "modifiers_price_grosz": 0,
            "item_total_grosz": item_total,
        })

    fee = delivery_fees.get(platform, 599)
    grand_total = items_total + fee

    return {
        "platform": platform,
        "is_open": True,
        "next_open": None,
        "items": comparison_items,
        "items_total_grosz": items_total,
        "delivery_fee_grosz": fee,
        "promotion_discount_grosz": 0,
        "grand_total_grosz": grand_total,
        "meets_minimum_order": grand_total >= 3000,
        "minimum_order_grosz": 3000,
        "estimated_delivery_minutes": delivery_minutes.get(platform, 40),
        "missing_items": [],
        "deep_link": f"https://{platform}.example.com/order",
    }


@dramatiq.actor(queue_name="comparison", max_retries=2)
def fetch_platform_mock(comparison_id: str, platform: str, request_json: str) -> None:
    """Mock: simulate fetching a single platform's prices.

    In production this calls the real scraper adapter.
    """
    redis = _get_sync_redis()
    results_key = f"comparison:{comparison_id}:results"
    channel = f"comparison:{comparison_id}"

    # ── Simulate network delay (1-3 seconds) ────────────────
    delay = random.uniform(1.0, 3.0)
    _time.sleep(delay)

    # ── Generate mock result ────────────────────────────────
    result = _generate_mock_result(platform, request_json)
    result_json = json.dumps(result)

    # ── CRITICAL: HSET *before* PUBLISH (race condition fix) ─
    redis.hset(results_key, platform, result_json)

    # ── PUBLISH event ───────────────────────────────────────
    event = {
        "event": "platform_status",
        "platform": platform,
        "data": result,
    }
    redis.publish(channel, json.dumps(event))

    # ── Check if all platforms done → finalize ──────────────
    all_fields = redis.hkeys(results_key)
    platforms_done = [f for f in all_fields if f != "_final"]

    if set(platforms_done) >= set(ENABLED_PLATFORMS):
        _finalize_comparison(redis, comparison_id, results_key, channel)

    redis.close()


def _finalize_comparison(
    redis: SyncRedis,
    comparison_id: str,
    results_key: str,
    channel: str,
) -> None:
    """Write _final summary and publish ready event."""
    # ── Read all platform results ───────────────────────────
    all_results = redis.hgetall(results_key)
    platforms_data: dict[str, dict] = {}
    cheapest_platform = None
    cheapest_total = None

    for field, raw in all_results.items():
        if field == "_final":
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        platforms_data[field] = data

        grand_total = data.get("grand_total_grosz", 0)
        if data.get("is_open") and (cheapest_total is None or grand_total < cheapest_total):
            cheapest_total = grand_total
            cheapest_platform = field

    # ── Calculate savings ───────────────────────────────────
    totals = [
        d.get("grand_total_grosz", 0)
        for d in platforms_data.values()
        if d.get("is_open")
    ]
    savings = (max(totals) - min(totals)) if len(totals) >= 2 else 0

    # ── Format savings_display in Polish ────────────────────
    PLATFORM_DISPLAY_NAMES = {
        "wolt": "Wolt",
        "pyszne": "Pyszne.pl",
        "ubereats": "Uber Eats",
        "glovo": "Glovo",
    }
    if savings > 0 and cheapest_platform:
        savings_zl = savings / 100
        platform_name = PLATFORM_DISPLAY_NAMES.get(cheapest_platform, cheapest_platform)
        savings_display = f"Zaoszczędź {savings_zl:.2f} zł na {platform_name}!".replace(".", ",")
    else:
        savings_display = ""

    # ── Write _final ────────────────────────────────────────
    final_payload = {
        "comparison_id": comparison_id,
        "cheapest_open": cheapest_platform,
        "savings_grosz": savings,
        "savings_display": savings_display,
        "platforms": platforms_data,
    }
    final_json = json.dumps(final_payload)

    # HSET _final BEFORE publish
    redis.hset(results_key, "_final", final_json)

    # PUBLISH ready event
    ready_event = {
        "event": "ready",
        "comparison_id": comparison_id,
        "cheapest_open": cheapest_platform,
        "savings_grosz": savings,
        "savings_display": savings_display,
    }
    redis.publish(channel, json.dumps(ready_event))

    # Set TTL on results hash
    redis.expire(results_key, RESULTS_TTL_SECONDS)
