import httpx
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Origin": "https://wolt.com",
    "Wolt-Language": "pl",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
}

# Search
r = httpx.get(
    "https://restaurant-api.wolt.com/v1/pages/restaurants?lat=52.2297&lon=21.0122",
    headers=headers,
    timeout=15,
)
data = r.json()

# Find 3 non-McDonalds venues with delivers=true
venues = []
for item in data["sections"][1]["items"]:
    v = item.get("venue", {})
    if v.get("delivers") and "mcdonald" not in v.get("slug", "").lower():
        venues.append(v)
    if len(venues) >= 3:
        break

# Try menu on each until we get sections
for v in venues:
    slug = v["slug"]
    print(f"=== MENU: {v['name']} ({slug}) ===")
    r2 = httpx.get(
        f"https://consumer-api.wolt.com/consumer-api/venue-content-api/v3/web/venue-content/slug/{slug}",
        headers=headers,
        timeout=15,
    )
    menu = r2.json()
    sections = menu.get("sections", [])
    print(f"  sections: {len(sections)}")

    if sections:
        # Found a working menu — dump structure
        sec = sections[0]
        print(f"  section[0] keys: {sorted(sec.keys())}")
        print(f"  section[0] name: {sec.get('name', '?')}")
        items = sec.get("items", [])
        print(f"  items: {len(items)}")
        if items:
            item = items[0]
            print(f"  item[0] keys: {sorted(item.keys())[:20]}")
            with open("diag_menu_item.json", "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False, indent=2)
            print("  Saved diag_menu_item.json")

            # Check for modifier structure
            for key in ["options", "option_groups", "modifiers", "modifier_groups"]:
                if key in item:
                    print(f"  >>> MODIFIERS in key: '{key}' count={len(item[key])}")
                    if item[key]:
                        print(f"      [0] keys: {sorted(item[key][0].keys()) if isinstance(item[key][0], dict) else '?'}")

        # Save first 2 sections
        with open("diag_menu_sections.json", "w", encoding="utf-8") as f:
            json.dump(sections[:2], f, ensure_ascii=False, indent=2)
        print("  Saved diag_menu_sections.json")
        break
    else:
        print("  (empty — trying next)")

print("\nDone!")