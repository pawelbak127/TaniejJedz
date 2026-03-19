import json
import sys

filename = sys.argv[1] if len(sys.argv) > 1 else "bella_ciao_response.json"

with open(filename, encoding="utf-8") as f:
    data = json.load(f)

print(f"Top keys: {sorted(data.keys())}")
print(f"next_page_token: {data.get('next_page_token')}")
print(f"sections: {len(data.get('sections', []))}")

for i, s in enumerate(data.get("sections", [])):
    items = s.get("items", [])
    options = s.get("options", [])
    print(f"\n  [{i}] {s.get('name', '?')}")
    print(f"      items: {len(items)}, options: {len(options)}")
    for item in items[:5]:
        disabled = " [NIEDOSTĘPNE]" if item.get("disabled_info") else ""
        mods = len(item.get("options", []))
        print(f"      - {item.get('name')}: {item.get('price', 0)/100:.2f} zł ({mods} mod){disabled}")
    if len(items) > 5:
        print(f"      ... +{len(items) - 5}")