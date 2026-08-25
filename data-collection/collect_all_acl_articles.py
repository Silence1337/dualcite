from acl_anthology import Anthology
import json

print("Загрузка данных ACL Anthology...")
anthology = Anthology.from_repo()
print("Данные загружены. Начинаем сбор всех публикаций...")

all_papers = []
for paper in anthology.papers():
    all_papers.append({
        'id': paper.full_id,
        'title': str(paper.title),
        'authors': [str(author) for author in paper.authors],
        'year': paper.year,
        'volume': paper.volume_id,
        'url': f"https://aclanthology.org/{paper.full_id}/"
    })

print(f"Всего собрано публикаций (включая воркшопы): {len(all_papers)}")
with open('acl_all_papers_full.json', 'w', encoding='utf-8') as f:
    json.dump(all_papers, f, indent=2, ensure_ascii=False)

print("Готово! Файл 'acl_all_papers_full.json' сохранён.")