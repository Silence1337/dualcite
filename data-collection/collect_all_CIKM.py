import requests
import json
import time

def get_articles_for_year(year, max_retries=3):
    """
    Собирает все статьи CIKM за указанный год с помощью DBLP API.
    Возвращает список статей (внутри года пагинация не нужна, так как статей < 1000).
    """
    base_url = "https://dblp.org/search/publ/api"
    # Запрос: venue:CIKM и year:YYYY
    query = f"venue:CIKM AND year:{year}"
    params = {
        "q": query,
        "format": "json",
        "h": 1000,  # максимум на страницу
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
                print(f"  Ошибка HTTP {resp.status_code} для года {year} (попытка {attempt+1})")
                time.sleep(2)
        except Exception as e:
            print(f"  Исключение для года {year}: {e} (попытка {attempt+1})")
            time.sleep(2)
    return []

def main():
    # Определяем диапазон годов, в которых проводилась CIKM (1992-2026)
    # Можно уточнить по странице: https://dblp.org/db/conf/cikm/
    start_year = 1992
    end_year = 2026
    all_articles = []

    print("Сбор статей CIKM по годам...")
    for year in range(end_year, start_year - 1, -1):
        print(f"  Год {year}:", end=" ")
        articles = get_articles_for_year(year)
        if articles:
            print(f"найдено {len(articles)} статей")
            all_articles.extend(articles)
        else:
            print("не найдено")
        time.sleep(1)  # пауза между годами

    print(f"\nВсего собрано статей CIKM: {len(all_articles)}")

    # Удаление дубликатов по DOI (если есть)
    unique_by_doi = {}
    for art in all_articles:
        doi = art.get('doi')
        if doi:
            if doi in unique_by_doi:
                continue
            else:
                unique_by_doi[doi] = art
        else:
            # Для статей без DOI оставляем как есть (дубликаты маловероятны)
            unique_by_doi[id(art)] = art  # просто для уникальности
    final_articles = list(unique_by_doi.values())
    print(f"После удаления дубликатов по DOI: {len(final_articles)}")

    # Сохраняем результат
    output_file = "cikm_all_years_works.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_articles, f, indent=2, ensure_ascii=False)
    print(f"Сохранено в {output_file}")

if __name__ == "__main__":
    main()