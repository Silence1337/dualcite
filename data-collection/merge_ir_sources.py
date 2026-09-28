"""
merge_ir_sources.py: merge the ACM, ECIR, and CIKM lists into the historical IR list.

Inputs: acm_ir_all_years.json, ecir_all_years_works.json, cikm_all_years_works.json
Output: ir_all_years_works.json (reference-lists/), later extended with WWW by
collect_ir_crossref.py www-history --merge ...
"""
import json
from pathlib import Path

# ACM papers
acm_file = Path("acm_ir_all_years.json")
if not acm_file.exists():
    print(f"{acm_file} not found.")
    exit()
with open(acm_file, 'r', encoding='utf-8') as f:
    acm_articles = json.load(f)
print(f"ACM papers: {len(acm_articles)}")

# ECIR papers
ecir_file = Path("ecir_all_years_works.json")
if not ecir_file.exists():
    print(f"{ecir_file} not found.")
    exit()
with open(ecir_file, 'r', encoding='utf-8') as f:
    ecir_articles = json.load(f)
print(f"ECIR papers: {len(ecir_articles)}")

# CIKM papers
cikm_file = Path("cikm_all_years_works.json")
if not cikm_file.exists():
    print(f"{cikm_file} not found. Run collect_cikm_all_years.py first.")
    exit()
with open(cikm_file, 'r', encoding='utf-8') as f:
    cikm_articles = json.load(f)
print(f"CIKM papers: {len(cikm_articles)}")

# merge
all_ir = acm_articles + ecir_articles + cikm_articles
print(f"IR papers after merging: {len(all_ir)}")

# save
output_file = "ir_all_years_works.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(all_ir, f, indent=2, ensure_ascii=False)
print(f"Saved to {output_file}")

# report duplicate DOIs
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
    print(f"Duplicate DOIs: {len(duplicates)}, e.g. {duplicates[:5]}")
else:
    print("No duplicate DOIs.")
