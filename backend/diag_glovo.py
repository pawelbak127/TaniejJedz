import httpx
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
}

# Check a few sitemaps for Warsaw store URLs
total_waw = 0
all_slugs = []

for letter in "abcdefghijklmnopqrs":
    url = f"https://glovoapp.com/sitemap-{letter}.xml"
    try:
        r = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
        if r.status_code != 200:
            print(f"  {letter}: {r.status_code}")
            continue
        # Find Warsaw store URLs
        waw = re.findall(r'<loc>https://glovoapp\.com/pl/pl/warszawa/stores/([^<]+?)/?</loc>', r.text)
        total_waw += len(waw)
        all_slugs.extend(waw)
        if waw:
            print(f"  sitemap-{letter}: {len(waw)} Warsaw stores (e.g. {waw[0]})")
        else:
            # Check total PL stores
            pl = re.findall(r'warszawa/stores/', r.text)
            print(f"  sitemap-{letter}: {len(pl)} Warsaw refs, {len(r.text)//1024}KB")
    except Exception as e:
        print(f"  sitemap-{letter}: ERROR {e}")

print(f"\nTotal Warsaw store slugs: {total_waw}")
if all_slugs:
    print(f"Examples: {all_slugs[:10]}")

# Also check sitemap-country-filter
print("\n=== COUNTRY FILTER SITEMAP ===")
r2 = httpx.get("https://glovoapp.com/sitemap-country-filter.xml", headers=headers, timeout=15, follow_redirects=True)
print(f"Status: {r2.status_code}, Size: {len(r2.text)}")
waw2 = re.findall(r'warszawa', r2.text)
print(f"'warszawa' mentions: {len(waw2)}")
if r2.status_code == 200:
    print(f"First 500: {r2.text[:500]}")

print("\nDone!")