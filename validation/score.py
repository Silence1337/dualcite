"""
score.py: compute accuracy from the labeled samples.

Population sizes are recomputed from the current index, and the precision of
each stratum is weighted by these sizes. Sampled links that are not found in the
current index, or that are marked "volume" (links from proceedings front matter),
are left out.

Run from the repository root:  python validation/score.py
"""
import csv, math, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dualcite.config import load_config
from dualcite.index import build_index

D = Path(__file__).resolve().parent
RANK = {"doi": 0, "exact": 1, "fuzzy": 2}
STRATA = {
    "doi": lambda m: m[2] == "doi",
    "exact": lambda m: m[2] == "exact" and m[5],
    "fuzzy 95-100": lambda m: m[2] == "fuzzy" and m[5] and m[3] >= 95,
    "fuzzy 90-95": lambda m: m[2] == "fuzzy" and m[5] and 90 <= m[3] < 95,
    "fuzzy 85-90": lambda m: m[2] == "fuzzy" and m[5] and 85 <= m[3] < 90,
    "fuzzy 80-85 (below threshold)": lambda m: m[2] == "fuzzy" and m[5] and 80 <= m[3] < 85,
    "rejected by year check": lambda m: not m[5],
}
FUZZY_BANDS = [("fuzzy 95-100", 95), ("fuzzy 90-95", 90), ("fuzzy 85-90", 85), ("fuzzy 80-85 (below threshold)", 80)]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n; den = 1 + z * z / n; c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, c - h), min(1.0, c + h)


def col(row, prefix):
    return row[next(k for k in row if k.startswith(prefix))].strip()


def main():
    cfg = load_config("config.yaml"); idx = build_index(cfg)
    papers, affil = idx["papers"], idx["affiliations"]
    best = {}
    for m in idx["match_log"]:
        k = (m[0], m[1])
        if k not in best or (RANK[m[2]], -m[3]) < (RANK[best[k][2]], -best[k][3]):
            best[k] = m
    pop = {s: sum(1 for m in best.values() if f(m)) for s, f in STRATA.items()}
    by_title = {}
    for pid, p in papers.items():
        by_title.setdefault(p["title"], []).append(pid)

    L = ["# Validation results", ""]
    stats, dropped, preprints, errors = {}, Counter(), 0, []
    for r in csv.DictReader(open(D / "citation_sample.csv", encoding="utf-8-sig")):
        lab, com = col(r, "label"), r.get("comment", "").strip()
        pairs = [(a, b) for a in by_title.get(r["citing_paper"], []) for b in by_title.get(r["matched_paper_title"], [])]
        if "volume" in com.lower() or not any(p in best for p in pairs):
            dropped[r["stratum"]] += 1; continue
        if lab not in ("0", "1"):
            continue
        s = stats.setdefault(r["stratum"], [0, 0]); s[0] += int(lab); s[1] += 1
        preprints += lab == "1" and "preprint" in com.lower()
        if lab == "0":
            errors.append(f"- [{r['stratum']}, {r['score']}] \"{r['title_in_reference'][:60]}\" vs \"{r['matched_paper_title'][:60]}\"" + (f" ({com})" if com else ""))
    L += ["## Citation matching: precision per stratum", "",
          "| Stratum | Population | Labeled | Correct | Precision | 95% interval |", "|---|---:|---:|---:|---:|---:|"]
    for s in STRATA:
        k, n = stats.get(s, (0, 0)); p, lo, hi = wilson(k, n)
        L.append(f"| {s} | {pop[s]:,} | {n} | {k} | {p:.1%} | {lo:.1%} to {hi:.1%} |")
    L += [""]
    if dropped:
        L.append(f"Sampled links not found in the current index: {sum(dropped.values())} {dict(dropped)}")
    L += [f"Correct fuzzy matches marked as a renamed preprint: {preprints}", "",
          "## Estimated precision of all accepted links by fuzzy threshold", "",
          "Stratum precisions weighted by current stratum sizes (year check applied).", "",
          "| Threshold | Accepted links | Estimated precision | Estimated false links |", "|---:|---:|---:|---:|"]
    for t in (80, 85, 90, 95, 101):
        use = ["doi", "exact"] + [b for b, lo in FUZZY_BANDS if lo >= t]
        tot = good = 0.0
        for s in use:
            if stats.get(s, (0, 0))[1]:
                tot += pop[s]; good += pop[s] * stats[s][0] / stats[s][1]
        name = "no fuzzy" if t == 101 else str(t)
        L.append(f"| {name} | {tot:,.0f} | {good / tot:.1%} | {tot - good:,.0f} |" if tot else f"| {name} | 0 | n/a | n/a |")

    def astratum(a):
        src = set(a.get("country_source", {}).values())
        return None if not src else "inferred" if "inferred" in src else "address" if "address" in src else "explicit"
    apop = Counter(astratum(a) for a in affil.values() if astratum(a))
    ids = {p["title"]: pid for pid, p in papers.items()}
    by, aerr = {}, []
    for r in csv.DictReader(open(D / "affiliation_sample.csv", encoding="utf-8-sig")):
        if r["paper_title"] not in ids:
            continue
        v, iv = col(r, "countries_correct"), col(r, "institutions_correct")
        s = by.setdefault(r["stratum"], [0, 0, 0, 0])
        if v in ("0", "1"):
            s[0] += int(v); s[1] += 1
        if iv in ("0", "1"):
            s[2] += int(iv); s[3] += 1
        if v == "0" or iv == "0":
            aerr.append(f"- [{r['stratum']}] countries {v or '-'} / institutions {iv or '-'}: wrong={r.get('wrong_countries', '')} missing={r.get('missing_countries', '')} {r.get('comment', '')}".rstrip())
    L += ["", "## Affiliations: accuracy by how the countries were found", "",
          "| Stratum | Population | Labeled | Countries correct | 95% interval | Institutions correct |", "|---|---:|---:|---:|---:|---:|"]
    tot = good = 0.0
    for s, (k, n, ik, im) in sorted(by.items()):
        p, lo, hi = wilson(k, n); tot += apop[s]; good += apop[s] * p
        L.append(f"| {s} | {apop[s]:,} | {n} | {p:.1%} | {lo:.1%} to {hi:.1%} | {ik / im:.1%} |" if im else f"| {s} | {apop[s]:,} | {n} | {p:.1%} | {lo:.1%} to {hi:.1%} | n/a |")
    if tot:
        L.append(f"\nWeighted country accuracy over all papers with a country: {good / tot:.1%}")
    L += ["", "## Errors found in the citation sample", ""] + errors + ["", "## Errors found in the affiliation sample", ""] + aerr
    (D / "validation_results.md").write_text("\n".join(L) + "\n", "utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
