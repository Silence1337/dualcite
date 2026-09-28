"""
download_acl.py: download the PDFs of the 2025 CL papers from the ACL Anthology.

Input: acl_papers_2025.json. Output: acl_pdfs_2025/<anthology_id>.pdf
"""
import json
import requests
from pathlib import Path
import time

JSON_FILE = "acl_papers_2025.json"
PDF_FOLDER = Path("acl_pdfs_2025")
DELAY = 1.0

PDF_FOLDER.mkdir(exist_ok=True)

with open(JSON_FILE, 'r', encoding='utf-8') as f:
    papers = json.load(f)

print(f"Papers: {len(papers)}")

for i, paper in enumerate(papers, 1):
    anthology_id = paper['anthology_id']
    pdf_url = f"https://aclanthology.org/{anthology_id}.pdf"
    pdf_path = PDF_FOLDER / f"{anthology_id}.pdf"

    if pdf_path.exists():
        continue

    try:
        print(f"[{i}/{len(papers)}] {anthology_id}")
        response = requests.get(pdf_url, timeout=30)
        if response.status_code == 200:
            with open(pdf_path, 'wb') as f:
                f.write(response.content)
            print(f"  -> saved ({len(response.content) / 1024:.1f} KB)")
        else:
            print(f"  -> HTTP error {response.status_code}")
    except Exception as e:
        print(f"  -> error: {e}")

    time.sleep(DELAY)
