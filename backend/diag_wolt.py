import httpx
import json
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html",
    "Accept-Language": "pl-PL,pl;q=0.9",
}

r = httpx.get(
    "https://wolt.com/pl/pol/krakow/restaurant/restauracja-sukiennice",
    headers=headers, timeout=20, follow_redirects=True,
)
html = r.text

# Extract React Query cache
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
data = None
for s in scripts:
    s = s.strip()
    if s.startswith("{") and '"queries"' in s[:200]:
        data = json.loads(s)
        break

queries = data["queries"]
# Find menu query
menu_q = None
for q in queries:
    if "venue-assortment" in str(q.get("queryKey", [])) and "category-listing" in str(q.get("queryKey", [])):
        menu_q = q.get("state", {}).get("data", {})
        break

print(f"Menu query keys: {sorted(menu_q.keys())}")
print(f"categories: {len(menu_q.get('categories', []))}")

# Items
items = menu_q.get("items", {})
print(f"items: {type(items).__name__}")
if isinstance(items, dict):
    print(f"  count: {len(items)}")
    first_id = next(iter(items))
    item = items[first_id]
    print(f"  first item keys: {sorted(item.keys())}")
    with open("diag_wolt_item.json", "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)
    print(f"  Saved diag_wolt_item.json")
elif isinstance(items, list):
    print(f"  count: {len(items)}")
    if items and isinstance(items[0], dict):
        print(f"  [0] keys: {sorted(items[0].keys())}")
        with open("diag_wolt_item.json", "w", encoding="utf-8") as f:
            json.dump(items[0], f, ensure_ascii=False, indent=2)
        print(f"  Saved diag_wolt_item.json")

# Options (modifiers)
options = menu_q.get("options", {})
print(f"\noptions: {type(options).__name__}")
if isinstance(options, dict):
    print(f"  count: {len(options)}")
    if options:
        first_opt = next(iter(options.values()))
        print(f"  first option keys: {sorted(first_opt.keys()) if isinstance(first_opt, dict) else type(first_opt)}")
elif isinstance(options, list):
    print(f"  count: {len(options)}")

# Variant groups
vg = menu_q.get("variant_groups", {})
print(f"\nvariant_groups: {type(vg).__name__}")
if isinstance(vg, dict):
    print(f"  count: {len(vg)}")
    if vg:
        first_vg = next(iter(vg.values()))
        print(f"  first vg keys: {sorted(first_vg.keys()) if isinstance(first_vg, dict) else type(first_vg)}")
        with open("diag_wolt_variant_group.json", "w", encoding="utf-8") as f:
            json.dump(first_vg, f, ensure_ascii=False, indent=2)
        print(f"  Saved diag_wolt_variant_group.json")

# Category details
cats = menu_q.get("categories", [])
print(f"\nCategories ({len(cats)}):")
total_items = 0
for c in cats:
    item_ids = c.get("item_ids", [])
    total_items += len(item_ids)
    print(f"  {c.get('name', '?'):30s} {len(item_ids)} items")
print(f"Total items across categories: {total_items}")

print("\nDone!")