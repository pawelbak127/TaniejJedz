import httpx
import json
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

# 1. GLOVO — check if KRK URL works
print("=== 1. GLOVO KRAKÓW ===")
for url in [
    "https://glovoapp.com/pl/pl/krakow/restaurants_702/",
    "https://glovoapp.com/pl/pl/krakow/",
]:
    r = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
    slugs = set(re.findall(r'/stores/([a-z0-9\-]+)', r.text))
    slugs = {s for s in slugs if len(s) > 3}
    print(f"  {r.status_code} ({len(r.text)//1024}KB) {r.url}")
    print(f"    Store slugs: {len(slugs)}")
    if slugs:
        for s in sorted(slugs)[:5]:
            print(f"      {s}")

# 2. UBER EATS — check suggestions for Kraków
print("\n=== 2. UBER EATS KRAKÓW ===")
ue_headers = {**headers, "Accept": "application/json", "Content-Type": "application/json", "x-csrf-token": "x"}
for query in ["pizza", "KFC", "burger", "sushi"]:
    r = httpx.post(
        "https://www.ubereats.com/_p/api/getSearchSuggestionsV1?localeCode=pl-en",
        json={"userQuery": query, "date": "", "startTime": 0, "endTime": 0},
        headers=ue_headers, timeout=10,
    )
    stores = [s for s in r.json().get("data", []) if s.get("type") == "store"]
    names = [s["store"]["title"] for s in stores if s.get("store")]
    print(f"  '{query}': {len(stores)} stores → {names[:3]}")

# 3. WOLT — Sukiennice menu check
print("\n=== 3. WOLT SUKIENNICE MENU ===")
wolt_headers = {
    **headers,
    "Accept": "application/json",
    "Origin": "https://wolt.com",
    "Wolt-Language": "pl",
    "app-language": "pl",
    "client-version": "1.16.87",
}
r = httpx.get(
    "https://consumer-api.wolt.com/consumer-api/venue-content-api/v3/web/venue-content/slug/restauracja-sukiennice",
    headers=wolt_headers, timeout=15,
)
data = r.json()
print(f"  Status: {r.status_code}")
print(f"  next_page_token: {data.get('next_page_token')}")
sections = data.get("sections", [])
print(f"  sections: {len(sections)}")
total_items = 0
for s in sections:
    items = s.get("items", [])
    total_items += len(items)
    print(f"    {s.get('name', '?')}: {len(items)} items")
print(f"  Total items: {total_items}")

# Check if there's pagination
if data.get("next_page_token"):
    print(f"\n  PAGINATION! Fetching next page...")
    r2 = httpx.get(
        "https://consumer-api.wolt.com/consumer-api/venue-content-api/v3/web/venue-content/slug/restauracja-sukiennice",
        params={"page_token": data["next_page_token"]},
        headers=wolt_headers, timeout=15,
    )
    d2 = r2.json()
    s2 = d2.get("sections", [])
    print(f"  Page 2: {len(s2)} sections, next_token={d2.get('next_page_token')}")
    for s in s2:
        print(f"    {s.get('name', '?')}: {len(s.get('items', []))} items")

print("\nDone!")