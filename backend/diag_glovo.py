"""
Diagnostyka — surowy response z Glovo /v3/stores/{slug}.
Uruchom:
  cd C:\Projects\TaniejJedz\backend
  python diag_glovo_raw.py
"""

import httpx
import json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Glovo-Location-City-Code": "KRK",
}

SLUGS = ["kfc-kra", "mcdonald-s-kra"]

for slug in SLUGS:
    url = f"https://api.glovoapp.com/v3/stores/{slug}?cityCode=KRK"
    print(f"\n{'='*60}")
    print(f"GET {url}")
    print(f"{'='*60}")

    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15)
        print(f"Status: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('content-type', '?')}")

        if resp.status_code == 200:
            try:
                data = resp.json()
                # Show top-level keys and types
                print(f"\nTop-level type: {type(data).__name__}")
                if isinstance(data, dict):
                    print(f"Keys ({len(data)}):")
                    for k in sorted(data.keys()):
                        v = data[k]
                        if isinstance(v, dict):
                            print(f"  {k}: dict (keys: {sorted(v.keys())[:8]})")
                        elif isinstance(v, list):
                            print(f"  {k}: list[{len(v)}]")
                            if v and isinstance(v[0], dict):
                                print(f"    [0] keys: {sorted(v[0].keys())[:8]}")
                        elif isinstance(v, str) and len(v) > 80:
                            print(f"  {k}: str ({len(v)} chars) = {v[:80]}...")
                        else:
                            print(f"  {k}: {repr(v)}")
                else:
                    print(f"Raw (first 500 chars): {json.dumps(data, ensure_ascii=False)[:500]}")

                # Save raw
                fname = f"diag_glovo_store_{slug}.json"
                with open(fname, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"\nSaved to: {fname}")

            except json.JSONDecodeError:
                print(f"NOT JSON. First 500 chars of body:")
                print(resp.text[:500])
        else:
            print(f"Body: {resp.text[:300]}")

    except Exception as exc:
        print(f"ERROR: {exc}")

print("\n✓ Done!")