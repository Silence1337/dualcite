"""
collect_cikm_all_years.py: list CIKM papers of all years from the dblp API.

Output: cikm_all_years_works.json, merged by merge_ir_sources.py.
Note: since 2026 dblp blocks automated requests, so this script may no longer run.
"""
import requests
import json
import time

def get_articles_for_year(year, max_retries=3):
    """Collect the CIKM papers of one year from the dblp API (fewer than 1000 per
    year, so no paging is needed)."""
    base_url = "https://dblp.org/search/publ/api"
    # query: venue:CIKM and year:YYYY
    query = f"venue:CIKM AND year:{year}"
    params = {
        "q": query,
        "format": "json",
        "h": 1000,  # maximum page size
        "f": 0
    }
    for attempt in range(max_retries):
        try:
            resp = requests.get(base_url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("result", {}).get("hits", {}).get("hit", [])
                articles = []
                for hit in hits:
                    info = hit.get("info", {})
                    articles.append({
                        "title": info.get("title"),
                        "doi": info.get("doi"),
                        "year": year,
                        "venue": info.get("venue"),
                        "url": info.get("url"),
                        "ee": info.get("ee")
                    })
                return articles
            else:
                print(f"  HTTP error {resp.status_code} for {year} (attempt {attempt+1})")
                time.sleep(2)
        except Exception as e:
            print(f"  Error for {year}: {e} (attempt {attempt+1})")
            time.sleep(2)
    return []

def main():
    # years in which CIKM took place, see https://dblp.org/db/conf/cikm/
    start_year = 1992
    end_year = 2026
    all_articles = []

    print("Collecting CIKM papers by year...")
    for year in range(end_year, start_year - 1, -1):
        print(f"  {year}:", end=" ")
        articles = get_articles_for_year(year)
        if articles:
            print(f"{len(articles)} papers")
            all_articles.extend(articles)
        else:
            print("none found")
        time.sleep(1)  # pause between years

    print(f"\nCIKM papers collected: {len(all_articles)}")

    # remove duplicates by DOI
    unique_by_doi = {}
    for art in all_articles:
        doi = art.get('doi')
        if doi:
            if doi in unique_by_doi:
                continue
            else:
                unique_by_doi[doi] = art
        else:
            # papers without a DOI are kept (duplicates are unlikely)
            unique_by_doi[id(art)] = art  # unique key
    final_articles = list(unique_by_doi.values())
    print(f"After removing DOI duplicates: {len(final_articles)}")

    # save
    output_file = "cikm_all_years_works.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_articles, f, indent=2, ensure_ascii=False)
    print(f"Saved to {output_file}")

if __name__ == "__main__":
    main()
