"""
collect_ir_crossref.py: collect IR papers from the Crossref API, where ACM and
Springer register the DOIs of their papers. Used for the parts of the dataset
that the older keyword and dblp collectors missed (dblp now also blocks
automated requests).

Proceedings volumes are first located in Crossref; their papers are then taken
by ISBN (Springer) or by scanning all ACM papers of the year and keeping those
whose DOI starts with the volume DOI (ACM), so no paper is lost to search ranking.

Modes (run from the repository root):

  papers        2025 papers of WWW (main and companion proceedings) and ECIR (all
                LNCS volumes), in the record format of data/papers/cluster_b.json.

      python data-collection/collect_ir_crossref.py papers --email you@example.com --merge data/papers/cluster_b.json

  www-history   WWW papers of all years for the historical IR list.

      python data-collection/collect_ir_crossref.py www-history --email you@example.com --merge reference-lists/ir_all_years_works.json

The SIGIR list of all years is built by make_flagship_lists.py, which reuses the
functions of this script.

--email is passed to Crossref, which then serves the requests from its faster
"polite" pool. A merged file is written in place after the original has been
saved as <file>.bak. Records are deduplicated by DOI.
"""
import argparse
import json
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

import requests

API = "https://api.crossref.org/works"
ROWS = 1000
FIELDS = "DOI,title,container-title,issued,type,event"


def year_of(item: dict) -> int | None:
    parts = (item.get("issued") or {}).get("date-parts") or [[None]]
    y = parts[0][0] if parts and parts[0] else None
    return int(y) if y else None


def to_record(item: dict, venue: str) -> dict | None:
    title = " ".join(item.get("title") or []).strip()
    if not title:
        return None
    return {"title": title, "doi": (item.get("DOI") or "").lower(), "year": year_of(item),
            "venue": venue, "source": "; ".join(item.get("container-title") or []),
            "ee": f"https://doi.org/{item.get('DOI')}"}


def crossref_get(params, email):
    params = dict(params)
    if email:
        params["mailto"] = email
    headers = {"User-Agent": f"DualCite data collection (mailto:{email or 'not given'})"}
    for attempt in range(6):
        try:
            r = requests.get(API, params=params, headers=headers, timeout=120)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 20)))
                continue
            r.raise_for_status()
            return r.json()["message"]
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"    attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    sys.exit("Crossref query failed after several attempts")


def find_volumes(prefix, query, accept, email):
    """Step 1: find the proceedings volumes themselves, with their DOI and ISBNs."""
    msg = crossref_get({"filter": f"prefix:{prefix},type:proceedings,type:book,type:edited-book",
                        "query.bibliographic": query, "rows": 200,
                        "select": "DOI,title,ISBN,issued,type"}, email)
    vols = []
    for it in msg.get("items", []):
        title = " ".join(it.get("title") or [])
        if accept(title, year_of(it)):
            vols.append({"title": title, "year": year_of(it), "isbns": it.get("ISBN") or [],
                         "doi": (it.get("DOI") or "").lower()})
    return vols


def scan_year(prefix, year, vols, email):
    """Fallback for publishers that do not put the ISBN on each paper (ACM): go
    through all papers of the prefix and year and keep those whose DOI starts
    with the DOI of a volume or whose proceedings title equals a volume title."""
    found = {v["title"]: {} for v in vols}
    titles = {v["title"].lower(): v["title"] for v in vols}
    cursor, pages = "*", 0
    while True:
        msg = crossref_get({"filter": f"prefix:{prefix},type:proceedings-article,"
                                      f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31",
                            "rows": ROWS, "cursor": cursor, "select": FIELDS}, email)
        items = msg.get("items", [])
        pages += 1
        for it in items:
            doi = (it.get("DOI") or "").lower()
            ct = [c.lower() for c in (it.get("container-title") or [])]
            for v in vols:
                if (v["doi"] and doi.startswith(v["doi"] + ".")) or v["title"].lower() in ct:
                    found[v["title"]][doi] = it
                    break
            else:
                for c in ct:
                    if c in titles:
                        found[titles[c]][doi] = it
        if pages % 10 == 0:
            print(f"      scanned {pages * ROWS:,} papers of {year} ...")
        cursor = msg.get("next-cursor")
        if not items or not cursor:
            break
        time.sleep(0.5)
    return {t: list(d.values()) for t, d in found.items()}


def items_of_volume(isbns, email):
    """Step 2: every item that carries one of the ISBNs of a volume (exact filter)."""
    out = {}
    for isbn in isbns:
        cursor = "*"
        while True:
            msg = crossref_get({"filter": f"isbn:{isbn}", "rows": ROWS, "cursor": cursor,
                                "select": FIELDS}, email)
            items = msg.get("items", [])
            for it in items:
                if it.get("type") in ("proceedings-article", "book-chapter"):
                    out[(it.get("DOI") or "").lower()] = it
            cursor = msg.get("next-cursor")
            if not items or not cursor:
                break
            time.sleep(1)
    return list(out.values())


def collect_volumes(prefix, query, accept, venue, email):
    vols = find_volumes(prefix, query, accept, email)
    if not vols:
        print("    no matching proceedings volume found")
    recs, pending = [], []
    for v in sorted(vols, key=lambda v: (v["year"] or 0, v["title"])):
        items = items_of_volume(v["isbns"], email) if v["isbns"] else []
        if items:
            print(f"    {len(items):5}  {v['title']} ({v['year']}; by ISBN)")
            recs += [r for r in (to_record(it, venue) for it in items) if r]
        else:
            pending.append(v)
    for year in sorted({v["year"] for v in pending if v["year"]}):
        vy = [v for v in pending if v["year"] == year]
        print(f"    scanning all {prefix} papers of {year} for {len(vy)} volume(s) ...")
        for title, items in scan_year(prefix, year, vy, email).items():
            print(f"    {len(items):5}  {title} ({year}; by DOI prefix / proceedings title)")
            recs += [r for r in (to_record(it, venue) for it in items) if r]
    return recs


def www_2025(title, year):
    return title.lower() in ("proceedings of the acm on web conference 2025",
                             "companion proceedings of the acm on web conference 2025")


def ecir_2025(title, year):
    return year == 2025 and "advances in information retrieval" in title.lower()


def www_any(title, year):
    t = title.lower()
    return bool(re.search(r"world wide web|web conference", t)) and not re.search(r"workshop|journal|transactions", t)


def dedupe(records):
    seen, out = set(), []
    for r in records:
        k = r["doi"] or r["title"].lower()
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def merge_into(path: Path, new: list[dict]) -> None:
    old = json.loads(path.read_text("utf-8"))
    have = {(r.get("doi") or "").lower() or (r.get("title") or "").lower() for r in old}
    add = [r for r in new if (r["doi"] or r["title"].lower()) not in have]
    shutil.copy(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text(json.dumps(old + add, ensure_ascii=False, indent=1), "utf-8")
    print(f"merged into {path}: {len(old)} existing + {len(add)} new = {len(old) + len(add)} "
          f"(backup: {path.name}.bak; {len(new) - len(add)} already present)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["papers", "www-history"])
    ap.add_argument("--email", help="contact e-mail for the Crossref polite pool (recommended)")
    ap.add_argument("--out", help="output JSON (default: ir_2025_www_ecir.json or www_all_years.json)")
    ap.add_argument("--merge", help="JSON list to merge the new records into")
    args = ap.parse_args()

    if args.mode == "papers":
        print("WWW 2025 (ACM), proceedings volumes:")
        www = collect_volumes("10.1145", "ACM on Web Conference 2025", www_2025, "WWW", args.email)
        print("ECIR 2025 (Springer), LNCS volumes:")
        ecir = collect_volumes("10.1007", "Advances in Information Retrieval ECIR 2025", ecir_2025, "ECIR", args.email)
        recs = dedupe(www + ecir)
        print(f"total: {len(recs)} papers {dict(Counter(r['venue'] for r in recs))}")
        out = Path(args.out or "ir_2025_www_ecir.json")
    else:
        print("WWW, all years (ACM), proceedings volumes:")
        recs = []
        for q in ("World Wide Web Conference", "The Web Conference", "ACM Web Conference"):
            recs += collect_volumes("10.1145", q, www_any, "WWW", args.email)
        recs = dedupe(recs)
        print(f"total: {len(recs)} WWW papers of all years")
        out = Path(args.out or "www_all_years.json")
    out.write_text(json.dumps(recs, ensure_ascii=False, indent=1), "utf-8")
    print(f"written: {out}")
    if args.merge:
        merge_into(Path(args.merge), recs)


if __name__ == "__main__":
    main()
