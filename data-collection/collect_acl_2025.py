from acl_anthology import Anthology
import json
import time

venues = ['acl', 'emnlp', 'coling', 'ijcnlp', 'naacl', 'lrec', 'eacl']
year = 2025

print("Загрузка данных Anthology...")
anthology = Anthology.from_repo()
print("Готово.\n")

all_papers = []

for venue in venues:
    event_id = f"{venue}-{year}"
    print(f"Обработка: {event_id}")
    try:
        event = anthology.get_event(event_id)
        if event is None:
            print(f"  → событие не найдено")
            continue
        for volume in event.volumes():
            for paper in volume.papers():
                all_papers.append({
                    'anthology_id': paper.full_id,
                    'title': str(paper.title),
                    'authors': [str(a) for a in paper.authors],
                    'year': year,
                    'venue': venue.upper(),
                    'doi': paper.doi,
                    'url': f"https://aclanthology.org/{paper.full_id}/"
                })
        print(f"  → найдено статей: {len([p for p in all_papers if p['venue'].lower()==venue])}")
    except Exception as e:
        print(f"  → ошибка: {e}")

with open('acl_papers_2025.json', 'w', encoding='utf-8') as f:
    json.dump(all_papers, f, indent=2, ensure_ascii=False)

print(f"\nВсего собрано: {len(all_papers)} статей. Сохранено в acl_papers_2025.json")