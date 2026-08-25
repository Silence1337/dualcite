import json

with open('ir_all_years_works.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

filtered = [p for p in data if p.get('year') == 2025]
print(f"Найдено статей за 2025 год: {len(filtered)}")

with open('ir_2025_works.json', 'w', encoding='utf-8') as f:
    json.dump(filtered, f, indent=2, ensure_ascii=False)