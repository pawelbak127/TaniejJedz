import httpx
import json
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "x-csrf-token": "x",
}

# 1. Search suggestions — works!
print("=== 1. SEARCH SUGGESTIONS ===")
r = httpx.post(
    "https://www.ubereats.com/_p/api/getSearchSuggestionsV1?localeCode=pl-en",
    json={"userQuery": "KFC", "date": "", "startTime": 0, "endTime": 0},
    headers=headers, timeout=10,
)
data = r.json()
print(f"Status: {r.status_code}, Size: {len(r.text)}")
inner = data.get("data", [])
print(f"data type: {type(inner).__name__}, len: {len(inner) if isinstance(inner, list) else '?'}")

if isinstance(inner, list):
    for i, item in enumerate(inner[:5]):
        if isinstance(item, dict):
            print(f"  [{i}] keys: {sorted(item.keys())[:10]}")
            print(f"      title: {item.get('title', '?')}")
            print(f"      uuid: {item.get('uuid', item.get('storeUuid', '?'))}")
    # Save first result
    if inner:
        with open("diag_ubereats_suggestion.json", "w", encoding="utf-8") as f:
            json.dump(inner[0], f, ensure_ascii=False, indent=2)
        print(f"\nSaved diag_ubereats_suggestion.json")

# 2. Try more queries
print("\n=== 2. MORE SEARCHES ===")
for query in ["pizza", "burger", "sushi"]:
    r2 = httpx.post(
        "https://www.ubereats.com/_p/api/getSearchSuggestionsV1?localeCode=pl-en",
        json={"userQuery": query, "date": "", "startTime": 0, "endTime": 0},
        headers=headers, timeout=10,
    )
    results = r2.json().get("data", [])
    stores = [x for x in results if isinstance(x, dict) and x.get("storeUuid", x.get("uuid"))]
    print(f"  '{query}': {len(results)} results, {len(stores)} with UUID")
    for s in stores[:3]:
        name = s.get("title", "?")
        uuid = s.get("storeUuid", s.get("uuid", "?"))
        print(f"    {name[:40]:40s} {uuid[:30]}")

# 3. Also try getSearchV1 (full search, not suggestions)
print("\n=== 3. FULL SEARCH ===")
r3 = httpx.post(
    "https://www.ubereats.com/_p/api/getSearchV1?localeCode=pl-en",
    json={"userQuery": "pizza", "date": "", "startTime": 0, "endTime": 0},
    headers=headers, timeout=10,
)
print(f"Status: {r3.status_code}, Size: {len(r3.text)}")
if r3.status_code == 200:
    d3 = r3.json()
    print(f"keys: {sorted(d3.keys())[:10]}")
    inner3 = d3.get("data", {})
    if isinstance(inner3, dict):
        print(f"data keys: {sorted(inner3.keys())[:10]}")
        stores_map = inner3.get("storesMap", {})
        print(f"storesMap: {len(stores_map)} stores")
        for uid, s in list(stores_map.items())[:5]:
            print(f"  {s.get('title', '?')[:40]:40s} {uid[:30]}")

# 4. HTML page for slug+uuid discovery
print("\n=== 4. HTML CITY PAGE ===")
r4 = httpx.get(
    "https://www.ubereats.com/pl-en/city/warsaw-emea",
    headers={**headers, "Accept": "text/html"},
    timeout=20, follow_redirects=True,
)
print(f"Status: {r4.status_code}, Size: {len(r4.text)//1024}KB, URL: {r4.url}")
slugs = set(re.findall(r'/store/([a-zA-Z0-9\-&%.]+)/([0-9a-f\-]{36})', r4.text))
print(f"Store slug+uuid pairs: {len(slugs)}")
for slug, uuid in list(slugs)[:10]:
    print(f"  {slug[:45]:45s} {uuid}")
if len(slugs) > 10:
    print(f"  ... +{len(slugs) - 10}")

print("\nDone!")