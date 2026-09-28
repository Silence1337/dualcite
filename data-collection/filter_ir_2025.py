"""
filter_ir_2025.py: keep the 2025 papers of the historical IR list.

Input: ir_all_years_works.json. Output: ir_2025_works.json (the basis of
data/papers/cluster_b.json; WWW and ECIR 2025 were added with
collect_ir_crossref.py papers --merge data/papers/cluster_b.json).
"""
import json

with open('ir_all_years_works.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# DBLP returns the year as a string ("2025"), Crossref as an integer (2025);
# compare as strings so that both sources pass the filter.
filtered = [p for p in data if str(p.get('year')) == '2025']
print(f"Papers from 2025: {len(filtered)}")

with open('ir_2025_works.json', 'w', encoding='utf-8') as f:
    json.dump(filtered, f, indent=2, ensure_ascii=False)
