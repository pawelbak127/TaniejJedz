import httpx
import json

r = httpx.get(
    "https://rest.api.eu-central-1.production.jet-external.com/discovery/pl/restaurants/enriched",
    params={"latitude": "52.2297", "longitude": "21.0122", "serviceType": "delivery"},
    headers={"Accept": "application/json", "Accept-Encoding": "gzip, deflate"},
    timeout=15,
)
data = r.json()
restaurants = data.get("restaurants", [])
print(f"Total restaurants: {len(restaurants)}")

# Show first 3 with all keys
for i, rest in enumerate(restaurants[:3]):
    print(f"\n=== Restaurant [{i}] ===")
    for k in sorted(rest.keys()):
        v = rest[k]
        if isinstance(v, dict):
            print(f"  {k}: dict keys={sorted(v.keys())[:8]}")
        elif isinstance(v, list):
            print(f"  {k}: list[{len(v)}]")
        else:
            print(f"  {k}: {repr(v)[:80]}")

# Save first restaurant for full inspection
with open("diag_pyszne_restaurant.json", "w", encoding="utf-8") as f:
    json.dump(restaurants[0] if restaurants else {}, f, ensure_ascii=False, indent=2)
print("\nSaved diag_pyszne_restaurant.json")

# Check how many have location
has_loc = sum(1 for r in restaurants if r.get("location") and isinstance(r["location"], dict) and r["location"].get("lat"))
print(f"\nWith location.lat: {has_loc}/{len(restaurants)}")

# Check alternative location fields
if restaurants:
    r0 = restaurants[0]
    for key in ["location", "address", "latitude", "lat", "geo", "coordinates"]:
        if key in r0:
            print(f"  Found '{key}': {repr(r0[key])[:100]}")