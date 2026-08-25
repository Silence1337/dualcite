import requests
import time
import json

def fetch_all_acm_ir():
    url = "https://api.crossref.org/works?filter=prefix:10.1145&rows=1000"
    works = []
    cursor = "*"

    keywords = ["sigir", "www", "wsdm", "the web conference", "international acm sigir", "acm international conference on web search and data mining"]

    while cursor:
        params = {"cursor": cursor}
        resp = requests.get(url, params=params, headers={"User-Agent": "YourApp/1.0 (mailto:andresa@ac.sce.ac.il)"})
        if resp.status_code != 200:
            print(f"Ошибка {resp.status_code}")
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
        print(f"Загружено {len(items)} записей, найдено {len(works)}...")
        cursor = data['message'].get('next-cursor')
        time.sleep(0.5)

    with open("acm_ir_all_years.json", "w") as f:
        json.dump(works, f, indent=2)
    print(f"Всего статей ACM IR: {len(works)}")
    return works

fetch_all_acm_ir()