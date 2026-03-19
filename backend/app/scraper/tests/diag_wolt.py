"""
Diagnostyka — sprawdza prawdziwe nazwy pól w API Wolt.
Uruchom: python app/scraper/tests/diag_wolt.py
"""

import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Origin": "https://wolt.com",
    "Wolt-Language": "pl",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
}

print("=== 1. SEARCH ===")
r = httpx.get(
    "https://restaurant-api.wolt.com/v1/pages/restaurants?lat=52.2297&lon=21.0122",
    headers=headers,
    timeout=15,
)
data = r.json()
venue = data["sections"][0]["items"][0]["venue"]

print(f"\nVenue keys ({len(venue)} total):")
for k in sorted(venue.keys()):
    v = venue[k]
    if isinstance(v, list):
        print(f"  {k}: list[{len(v)}]  first={repr(v[0])[:60] if v else 'empty'}")
    elif isinstance(v, dict):
        print(f"  {k}: dict keys={sorted(v.keys())[:8]}")
    else:
        print(f"  {k}: {repr(v)[:80]}")

print(f"\n=== 2. MENU for: {venue['slug']} ===")
r2 = httpx.get(
    f"https://consumer-api.wolt.com/consumer-api/venue-content-api/v3/web/venue-content/slug/{venue['slug']}",
    headers=headers,
    timeout=15,
)
menu = r2.json()

print(f"\nTop-level keys ({len(menu)} total):")
for k in sorted(menu.keys()):
    v = menu[k]
    if isinstance(v, list):
        print(f"  {k}: list[{len(v)}]")
        if v and isinstance(v[0], dict):
            print(f"    [0] keys: {sorted(v[0].keys())[:15]}")
    elif isinstance(v, dict):
        print(f"  {k}: dict keys={sorted(v.keys())[:10]}")
    else:
        print(f"  {k}: {repr(v)[:60]}")

# Save raw responses for analysis
with open("diag_wolt_search_venue.json", "w", encoding="utf-8") as f:
    json.dump(venue, f, ensure_ascii=False, indent=2)

with open("diag_wolt_menu_top.json", "w", encoding="utf-8") as f:
    json.dump({k: v if not isinstance(v, list) else f"list[{len(v)}]" for k, v in menu.items()}, f, ensure_ascii=False, indent=2)

print("\nZapisano: diag_wolt_search_venue.json, diag_wolt_menu_top.json")
print("Done!")
