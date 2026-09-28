"""
collect_ecir_all_years.py: list ECIR papers of all years from the dblp API.

Output: ecir_all_years_works.json, merged by merge_ir_sources.py.
Note: since 2026 dblp blocks automated requests, so this script may no longer run.
"""
import requests
import json
import time
from collections import Counter

def get_ecir_all_years():
    base_url = "https://dblp.org/search/publ/api"
    works = []
    start = 0
    page_size = 1000
    total_hits = None
    page = 0

    print("Collecting ECIR papers (dblp API)...")
    while True:
        params = {
            "q": "ecir",
            "format": "json",
            "h": page_size,
            "f": start
        }
        try:
            response = requests.get(base_url, params=params, timeout=30)
            if response.status_code != 200:
                print(f"  HTTP error {response.status_code}")
                break
            data = response.json()
            if total_hits is None:
                total_hits = int(data.get("result", {}).get("@total", 0))
                print(f"  Total hits: {total_hits}")
            hits = data.get("result", {}).get("hits", {}).get("hit", [])
            if not hits:
                break
            for hit in hits:
                info = hit.get("info", {})
                works.append({
                    "title": info.get("title"),
                    "doi": info.get("doi"),
                    "year": int(info["year"]) if str(info.get("year", "")).isdigit() else info.get("year"),
                    "venue": info.get("venue"),
                    "url": info.get("url"),
                    "ee": info.get("ee")
                })
            print(f"  -> page {page+1}: {len(hits)} records, {len(works)} in total")
            start += page_size
            page += 1
            # if start >= total_hits:
            #     break
            time.sleep(0.5)
        except Exception as e:
            print(f"  Error: {e}")
            break
    return works

ecir_works = get_ecir_all_years()
print(f"\nECIR papers of all years: {len(ecir_works)}")

output_file = "ecir_all_years_works.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(ecir_works, f, indent=2, ensure_ascii=False)
print(f"Saved to {output_file}")

years_counter = Counter(work['year'] for work in ecir_works if work['year'])
print("\nPapers per year (top 10):")
for year, cnt in years_counter.most_common(10):
    print(f"  {year}: {cnt}")
