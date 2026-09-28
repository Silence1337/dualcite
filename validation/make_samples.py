"""
make_samples.py: draw the samples for manual validation.

Writes two CSV files (open them in Excel or Google Sheets) and a JSON file with
the population sizes of each stratum, which score.py needs for weighting:

  citation_sample.csv     candidate citation links, stratified by match type,
                          fuzzy score band, and year-check outcome
  affiliation_sample.csv  papers, stratified by how their countries were found
  populations.json

Run from the repository root:  python validation/make_samples.py
Existing samples that already contain labels are not overwritten unless --force is given.
"""
import csv, json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dualcite.config import load_config
from dualcite.index import build_index

SEED = 42
OUT = Path(__file__).resolve().parent


def already_labeled(path):
    """True if a sample file exists and contains at least one label."""
    if not path.exists():
        return False
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        if any(v.strip() for k, v in row.items() if k and ("correct" in k or k.startswith("label"))):
            return True
    return False


def main():
    force = "--force" in sys.argv[1:]
    for name in ("citation_sample.csv", "affiliation_sample.csv"):
        if already_labeled(OUT / name) and not force:
            sys.exit(f"{name} already contains labels and would be overwritten. "
                     "Use score.py to evaluate it, or run with --force to draw a new sample.")
    cfg = load_config("config.yaml")
    idx = build_index(cfg)
    papers, log_, affil = idx["papers"], idx["match_log"], idx["affiliations"]
    rnd = random.Random(SEED)

    # ---- citation links: one entry per (citing, cited) pair, best evidence kept ----
    best = {}
    rank = {"doi": 0, "exact": 1, "fuzzy": 2}
    for m in log_:
        k = (m[0], m[1])
        if k not in best or (rank[m[2]], -m[3]) < (rank[best[k][2]], -best[k][3]):
            best[k] = m
    strata = {
        "doi": lambda m: m[2] == "doi",
        "exact": lambda m: m[2] == "exact" and m[5],
        "fuzzy 95-100": lambda m: m[2] == "fuzzy" and m[5] and m[3] >= 95,
        "fuzzy 90-95": lambda m: m[2] == "fuzzy" and m[5] and 90 <= m[3] < 95,
        "fuzzy 85-90": lambda m: m[2] == "fuzzy" and m[5] and 85 <= m[3] < 90,
        "fuzzy 80-85 (below threshold)": lambda m: m[2] == "fuzzy" and m[5] and 80 <= m[3] < 85,
        "rejected by year check": lambda m: not m[5],
    }
    size = {"doi": 30, "exact": 40, "rejected by year check": 20}
    pops, rows = {}, []
    for name, cond in strata.items():
        pool = [m for m in best.values() if cond(m)]
        pops[name] = len(pool)
        for m in rnd.sample(pool, min(size.get(name, 30), len(pool))):
            src, tgt = papers[m[0]], papers[m[1]]
            rows.append({
                "id": f"C{len(rows) + 1:03d}", "stratum": name, "score": m[3],
                "reference_year": m[4] or "", "title_in_reference": m[6],
                "matched_paper_title": tgt["title"], "matched_paper_venue_year": f"{tgt['venue'].upper()} {tgt.get('year', '')}",
                "matched_paper_link": tgt.get("url", ""),
                "citing_paper": src["title"], "citing_paper_link": src.get("url", ""),
                "label (1 = same paper, 0 = different, ? = unclear)": "", "comment": "",
            })
    if not rows:
        sys.exit("no candidate links found")
    with open(OUT / "citation_sample.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)

    # ---- affiliations: stratified by how the countries were identified ----
    def stratum(a):
        src = set(a.get("country_source", {}).values())
        if not src:
            return None
        if "inferred" in src:
            return "inferred"
        if "address" in src:
            return "address"
        return "explicit"
    groups = {}
    for pid, a in affil.items():
        s = stratum(a)
        if s:
            groups.setdefault(s, []).append(pid)
    asize = {"explicit": 40, "inferred": 40, "address": 20}
    arows = []
    for s, pids in sorted(groups.items()):
        pops[f"affiliation: {s}"] = len(pids)
        for pid in rnd.sample(pids, min(asize[s], len(pids))):
            p, a = papers[pid], affil[pid]
            arows.append({
                "id": f"A{len(arows) + 1:03d}", "stratum": s, "paper_title": p["title"],
                "venue": p["venue"].upper(), "link": p.get("url", ""),
                "countries_found (source)": "; ".join(f"{c} ({h})" for c, h in sorted(a["country_source"].items())),
                "institutions_found": "; ".join(a["institutions"]),
                "countries_correct (1 = all correct, 0 = not)": "", "wrong_countries": "", "missing_countries": "",
                "institutions_correct (1 = yes, 0 = no)": "", "comment": "",
            })
    with open(OUT / "affiliation_sample.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(arows[0])); wr.writeheader(); wr.writerows(arows)
    (OUT / "populations.json").write_text(json.dumps(pops, indent=2), "utf-8")
    print(f"citation_sample.csv: {len(rows)} rows; affiliation_sample.csv: {len(arows)} rows")
    print("populations:", pops)


if __name__ == "__main__":
    main()
