"""
collect_acl_all_years.py: list every paper of the ACL Anthology (all years,
including workshops and journals), the historical CL list.

Output: acl_all_papers_full.json (reference-lists/).
Requires: pip install acl-anthology
"""
from acl_anthology import Anthology
import json

print("Loading the ACL Anthology...")
anthology = Anthology.from_repo()
print("Loaded. Collecting all publications...")

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

print(f"Collected {len(all_papers)} publications (including workshops and journals)")
with open('acl_all_papers_full.json', 'w', encoding='utf-8') as f:
    json.dump(all_papers, f, indent=2, ensure_ascii=False)

print("Saved to acl_all_papers_full.json")
