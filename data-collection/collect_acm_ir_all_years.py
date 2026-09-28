"""
collect_acm_ir_all_years.py: list ACM papers of the IR conferences (SIGIR, WSDM,
WWW, ...) from Crossref by keywords in the proceedings title.

Output: acm_ir_all_years.json, merged by merge_ir_sources.py.
Note: the year is taken from the Crossref "created" date (DOI registration), which
for old ACM papers is often 2003; and the keywords miss proceedings with other
names. The complete SIGIR and WWW lists were therefore collected again with
collect_ir_crossref.py and make_flagship_lists.py.
"""
import requests
import time
import json

def fetch_all_acm_ir():
    url = "https://api.crossref.org/works?filter=prefix:10.1145&rows=1000"
    works = []
    cursor = "*"

    # Since 2023 the WWW proceedings are titled "Proceedings of the ACM (on) Web Conference",
    # which "the web conference" does not match, so "web conference" is used instead.
    keywords = ["sigir", "www", "wsdm", "web conference", "world wide web conference", "international acm sigir", "acm international conference on web search and data mining"]

    while cursor:
        params = {"cursor": cursor}
        resp = requests.get(url, params=params, headers={"User-Agent": "DualCite data collection (mailto:andresa@ac.sce.ac.il)"})
        if resp.status_code != 200:
            print(f"HTTP error {resp.status_code}")
            break
        data = resp.json()
        items = data['message']['items']
        if not items:
            break
        for item in items:
            container = item.get('container-title', [None])[0]
            if container and any(kw in container.lower() for kw in keywords):
                works.append({
                    'title': item.get('title', [None])[0],
                    'doi': item.get('DOI'),
                    'year': item.get('created', {}).get('date-parts', [[None]])[0][0],
                    'source': container,
                    'venue': 'ACM'
                })
        print(f"Read {len(items)} records, {len(works)} matched so far...")
        cursor = data['message'].get('next-cursor')
        time.sleep(0.5)

    with open("acm_ir_all_years.json", "w") as f:
        json.dump(works, f, indent=2)
    print(f"ACM IR papers: {len(works)}")
    return works

fetch_all_acm_ir()
