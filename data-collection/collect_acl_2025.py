"""
collect_acl_2025.py: list the 2025 papers of the CL venues from the ACL Anthology
(all volumes of each event, including Findings and co-located workshops).

Output: acl_papers_2025.json (used as data/papers/cluster_a.json).
Requires: pip install acl-anthology
"""
from acl_anthology import Anthology
import json

venues = ['acl', 'emnlp', 'coling', 'ijcnlp', 'naacl', 'lrec', 'eacl']
year = 2025

print("Loading the ACL Anthology...")
anthology = Anthology.from_repo()
print("Done.\n")

all_papers = []

for venue in venues:
    event_id = f"{venue}-{year}"
    print(f"Processing: {event_id}")
    try:
        event = anthology.get_event(event_id)
        if event is None:
            print("  -> event not found")
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
        print(f"  -> papers found: {len([p for p in all_papers if p['venue'].lower()==venue])}")
    except Exception as e:
        print(f"  -> error: {e}")

with open('acl_papers_2025.json', 'w', encoding='utf-8') as f:
    json.dump(all_papers, f, indent=2, ensure_ascii=False)

print(f"\nCollected {len(all_papers)} papers; saved to acl_papers_2025.json")
