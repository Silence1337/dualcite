import json
from pathlib import Path

# Загрузка ACM статей
acm_file = Path("acm_ir_all_years.json")
if not acm_file.exists():
    print(f"Файл {acm_file} не найден.")
    exit()
with open(acm_file, 'r', encoding='utf-8') as f:
    acm_articles = json.load(f)
print(f"Загружено ACM статей: {len(acm_articles)}")

# Загрузка ECIR статей
ecir_file = Path("ecir_all_years_works.json")
if not ecir_file.exists():
    print(f"Файл {ecir_file} не найден.")
    exit()
with open(ecir_file, 'r', encoding='utf-8') as f:
    ecir_articles = json.load(f)
print(f"Загружено ECIR статей: {len(ecir_articles)}")

# Загрузка CIKM статей
cikm_file = Path("cikm_all_years_works.json")
if not cikm_file.exists():
    print(f"Файл {cikm_file} не найден. Сначала запустите сбор CIKM.")
    exit()
with open(cikm_file, 'r', encoding='utf-8') as f:
    cikm_articles = json.load(f)
print(f"Загружено CIKM статей: {len(cikm_articles)}")

# Объединение
all_ir = acm_articles + ecir_articles + cikm_articles
print(f"Всего IR статей после объединения: {len(all_ir)}")

# Сохранение результата
output_file = "ir_all_years_works.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(all_ir, f, indent=2, ensure_ascii=False)
print(f"Объединённый файл сохранён: {output_file}")

# Простая проверка дубликатов по DOI (если есть)
dois = set()
duplicates = []
for article in all_ir:
    doi = article.get('doi')
    if doi:
        if doi in dois:
            duplicates.append(doi)
        else:
            dois.add(doi)
if duplicates:
    print(f"Найдено дубликатов DOI: {len(duplicates)}. Примеры: {duplicates[:5]}")
else:
    print("Дубликатов DOI не обнаружено.")