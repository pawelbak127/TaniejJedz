import json
try:
    from curl_cffi.requests import Session
    html = Session(impersonate="chrome110").get(
        "https://www.pyszne.pl/menu/nocny-szafran-pizza-thai-indian-warszawa-sokolowska",
        timeout=15,
    ).text
except ImportError:
    import httpx
    html = httpx.get(
        "https://www.pyszne.pl/menu/nocny-szafran-pizza-thai-indian-warszawa-sokolowska",
        headers={"User-Agent": "Mozilla/5.0 Chrome/124.0.0.0"}, timeout=15, follow_redirects=True,
    ).text

from bs4 import BeautifulSoup
data = json.loads(BeautifulSoup(html, "lxml").find("script", id="__NEXT_DATA__").string)

rest = data["props"]["appProps"]["preloadedState"]["menu"]["restaurant"]
cdn = rest["cdn"]

# Check menus for categories
menus = cdn.get("restaurant", {}).get("menus", [])
if not menus:
    menus = rest.get("menus", [])
if not menus:
    # Try cdn.restaurant
    r_inner = cdn.get("restaurant", {})
    menus = r_inner.get("menus", [])

print(f"menus: {'list' if isinstance(menus, list) else type(menus).__name__}[{len(menus)}]")
if menus:
    menu0 = menus[0]
    print(f"  menus[0] keys: {sorted(menu0.keys())}")
    cats = menu0.get("categories", menu0.get("menuGroups", []))
    print(f"  categories/menuGroups: {len(cats)}")
    if cats:
        print(f"    [0] keys: {sorted(cats[0].keys())[:10]}")
        print(f"    [0] name: {cats[0].get('name', '?')}")
        items_in_cat = cats[0].get("items", cats[0].get("itemIds", []))
        print(f"    [0] items: {len(items_in_cat)}")
        if items_in_cat:
            print(f"      [0]: {repr(items_in_cat[0])[:80]}")
        with open("diag_pyszne_category.json", "w", encoding="utf-8") as f:
            json.dump(cats[0], f, ensure_ascii=False, indent=2)
        print("    Saved diag_pyszne_category.json")

# Also check layout key
layout = rest.get("layout", {})
print(f"\nlayout keys: {sorted(layout.keys())[:10]}" if isinstance(layout, dict) else f"\nlayout: {type(layout)}")

print("\nDone!")