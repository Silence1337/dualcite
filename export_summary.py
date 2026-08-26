"""
export_summary.py — dump all the valuable aggregates from a built DualCite index
into a single compact Markdown file (results_summary.md).

This is the file to feed to an AI (or read yourself) when looking for patterns
to write up in the thesis Results/Discussion. It contains only aggregates, not
the raw 14k papers, so it stays small.

Run from the dualcite folder:
    python export_summary.py
    python export_summary.py --config config.yaml --out results_summary.md
"""
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import pycountry

from dualcite.config import load_config
from dualcite.index import (build_index, compute_citation_stats, resolve_venue,
                            norm_title, load_papers, parse_refs)
from dualcite.tabs.geomap import build_geo_aux

TEI = "{http://www.tei-c.org/ns/1.0}"


def cname(a2):
    try:
        c = pycountry.countries.get(alpha_2=a2)
        return c.name if c else a2
    except Exception:
        return a2


def _load_ref_titles(path):
    """Return (normalized_titles_set, dois_set) from an all-years reference list."""
    data = json.loads(Path(path).read_text("utf-8"))
    titles, dois = set(), set()
    for x in data:
        t = x.get("title")
        if t:
            n = norm_title(t)
            if n:
                titles.add(n)
        d = (x.get("doi") or "").strip().lower()
        if d:
            dois.add(d)
    return titles, dois


def count_all_years(cfg, index, cl_refs_path, ir_refs_path):
    """
    Classify every outgoing reference from the 2025 papers against full
    all-years reference lists, as internal / external / other. Returns
    {cluster: {internal, external, other}}.
    """
    papers = index["papers"]
    _, _, ref_paths = load_papers(cfg)

    a_titles, a_dois = _load_ref_titles(cl_refs_path)
    b_titles, b_dois = _load_ref_titles(ir_refs_path)

    counts = {"a": defaultdict(int), "b": defaultdict(int)}
    for pid, p in papers.items():
        ck = p["cluster"]
        refs = parse_refs(ref_paths[pid])
        seen = set()
        for title, doi in refs:
            doi = (doi or "").strip().lower()
            n = norm_title(title)
            key = doi or n
            if not key or key in seen:
                continue
            seen.add(key)
            in_a = (doi and doi in a_dois) or (n and n in a_titles)
            in_b = (doi and doi in b_dois) or (n and n in b_titles)
            own_hit = in_a if ck == "a" else in_b
            other_hit = in_b if ck == "a" else in_a
            if own_hit:
                counts[ck]["internal"] += 1
            elif other_hit:
                counts[ck]["external"] += 1
            else:
                counts[ck]["other"] += 1
    return counts, (len(a_titles), len(a_dois), len(b_titles), len(b_dois))


def count_venue_references(cfg, index):
    """
    Count how often each venue is CITED across the whole corpus, regardless of
    the cited paper's year. Reads the cited venue name from each reference in
    the GROBID XML (monogr/title) and matches it to a venue via the config
    patterns.

    This is the "2025 -> all years" view: unlike the citation graph (which only
    links 2025->2025 papers inside the corpus), this counts every reference to
    one of the tracked venues no matter when the cited work was published.

    Returns {source_cluster: {cited_venue: count}} plus totals.
    """
    papers = index["papers"]
    refs_root = cfg.path("refs_xml")

    # source_cluster -> cited_venue -> count
    result = {"a": defaultdict(int), "b": defaultdict(int)}
    # also track how many references had ANY resolvable venue
    totals = {"a": {"refs": 0, "venue_hits": 0},
              "b": {"refs": 0, "venue_hits": 0}}

    for pid, p in papers.items():
        ck = p["cluster"]
        xml_path = refs_root / ck / f"{pid}.xml"
        if not xml_path.exists():
            continue
        try:
            tree = ET.parse(xml_path)
        except Exception:
            continue
        for bib in tree.iter(f"{TEI}biblStruct"):
            # cited venue name: journal title, else monograph title
            venue_name = None
            for lvl in ("j", "m"):
                el = bib.find(f".//{TEI}title[@level='{lvl}']")
                if el is not None and el.text:
                    venue_name = el.text.strip()
                    break
            if not venue_name:
                continue
            totals[ck]["refs"] += 1
            v = resolve_venue(venue_name, cfg)
            if v:
                result[ck][v] += 1
                totals[ck]["venue_hits"] += 1

    return result, totals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--out", default="results_summary.md")
    ap.add_argument("--cl-refs", default=None,
                    help="Optional: all-years reference list JSON for cluster A. "
                         "If both --cl-refs and --ir-refs are given, an "
                         "internal/external/other breakdown across all years is "
                         "added to the summary.")
    ap.add_argument("--ir-refs", default=None,
                    help="Optional: all-years reference list JSON for cluster B.")
    args = ap.parse_args()

    cfg = load_config(args.config)
    index = build_index(cfg)
    stats = compute_citation_stats(index)
    geo = build_geo_aux(index, stats)

    papers = index["papers"]
    citations = index["citations"]
    flows = index["flows"]
    affil = index["affiliations"]

    a, b = cfg.clusters["a"], cfg.clusters["b"]
    A, B = a.short, b.short

    L = []  # lines
    def w(s=""):
        L.append(s)

    w(f"# DualCite results summary")
    w()
    w(f"Two venue groups compared: **{a.name} ({A})** vs "
      f"**{b.name} ({B})**.")
    w()

    # ---------- corpus overview ----------
    n_a = sum(1 for p in papers.values() if p["cluster"] == "a")
    n_b = sum(1 for p in papers.values() if p["cluster"] == "b")
    w("## Corpus overview")
    w()
    w(f"- Total papers in corpus: {len(papers):,}")
    w(f"- {A} papers: {n_a:,}")
    w(f"- {B} papers: {n_b:,}")
    with_country = sum(1 for pid in papers
                       if affil.get(pid, {}).get("countries"))
    w(f"- Papers with country data: {with_country:,} "
      f"({with_country/len(papers)*100:.1f}%)")
    total_edges = sum(len(v) for v in citations.values())
    w(f"- Intra-corpus citations (edges): {total_edges:,}")
    total_refs_all = sum(index.get("total_refs", {}).values())
    if total_refs_all:
        other = total_refs_all - total_edges
        w(f"- Total references made (all, including outside the corpus): "
          f"{total_refs_all:,}")
        w(f"- References resolved within the corpus: {total_edges:,} "
          f"({total_edges/total_refs_all*100:.1f}%)")
        w(f"- References to works outside the corpus (\"other\"): {other:,} "
          f"({other/total_refs_all*100:.1f}%)")
    w()
    if total_refs_all:
        w("> The vast majority of references point outside the single-year "
          "corpus (to earlier years or untracked venues). This is expected: "
          "most citations in any paper are to prior work. The citation-flow "
          "analysis below therefore concerns only the small fraction of "
          "references that link two papers *inside* the 2025 corpus — the "
          "asymmetry and relative shares matter more than the absolute counts.")
        w()

    # ---------- citation flows ----------
    w("## Citation flows between the two communities")
    w()
    w("*(Only references that resolve to another paper inside the corpus — "
      "i.e. 2025→2025 links. The \"other\" bucket above is excluded here.)*")
    w()
    tot = sum(flows.values()) or 1
    w(f"| Direction | Citations | % of all intra-corpus citations |")
    w(f"|---|---:|---:|")
    w(f"| {A} → {A} (within {A}) | {flows['a_a']:,} | {flows['a_a']/tot*100:.1f}% |")
    w(f"| {B} → {B} (within {B}) | {flows['b_b']:,} | {flows['b_b']/tot*100:.1f}% |")
    w(f"| {A} → {B} (cross) | {flows['a_b']:,} | {flows['a_b']/tot*100:.1f}% |")
    w(f"| {B} → {A} (cross) | {flows['b_a']:,} | {flows['b_a']/tot*100:.1f}% |")
    w()
    cross = flows["a_b"] + flows["b_a"]
    w(f"- Total cross-community citations: {cross:,} "
      f"({cross/tot*100:.1f}% of all)")
    if flows["a_b"] and flows["b_a"]:
        ratio = flows["a_b"] / flows["b_a"]
        w(f"- Cross-flow asymmetry ({A}→{B} vs {B}→{A}): "
          f"{flows['a_b']:,} vs {flows['b_a']:,}  (ratio {ratio:.2f})")
    w()

    # ---------- 2025 -> all years (venue reference counting) ----------
    w("## References to tracked venues across all years")
    w()
    w("Unlike the citation flows above (which only link 2025→2025 papers inside "
      "the corpus), this counts every reference our 2025 papers make to one of "
      "the tracked venues **regardless of the cited work's year**. It is the "
      "broader 'do these communities cite each other's venues at all' view, and "
      "the numbers are naturally much larger.")
    w()
    vref, vtot = count_venue_references(cfg, index)

    def venue_ref_block(src_ck, src_short):
        own = a.venues if src_ck == "a" else b.venues
        other = b.venues if src_ck == "a" else a.venues
        own_hits = sum(vref[src_ck].get(v, 0) for v in own)
        other_hits = sum(vref[src_ck].get(v, 0) for v in other)
        tot = own_hits + other_hits or 1
        w(f"### References made by {src_short} papers")
        w()
        w(f"- To own community ({src_short}) venues: {own_hits:,} "
          f"({own_hits/tot*100:.1f}%)")
        w(f"- To other community venues: {other_hits:,} "
          f"({other_hits/tot*100:.1f}%)")
        w()
        w(f"| Cited venue | Cluster | References |")
        w(f"|---|---|---:|")
        for v in a.venues + b.venues:
            n = vref[src_ck].get(v, 0)
            if n == 0:
                continue
            cl = A if v in a.venues else B
            w(f"| {v.upper()} | {cl} | {n:,} |")
        w()

    venue_ref_block("a", A)
    venue_ref_block("b", B)

    w("*Note: this counts references whose cited venue name could be matched to "
      "a tracked venue. References to venues outside the tracked set, or that "
      "GROBID couldn't parse a venue name for, are not counted here.*")
    w()

    # ---------- optional: all-years internal/external/other ----------
    if args.cl_refs and args.ir_refs:
        w("## Internal / external / other — matched against all-years lists")
        w()
        w("Every outgoing reference from the 2025 papers, matched against full "
          f"all-years reference lists of **{A}** and **{B}** and classified as "
          "internal (same community, any year), external (other community, any "
          "year), or other (in neither list). This is the most complete view "
          "of how the two communities cite each other.")
        w()
        counts, sizes = count_all_years(cfg, index, args.cl_refs, args.ir_refs)
        w(f"*(Reference lists: {A} — {sizes[0]:,} titles / {sizes[1]:,} DOIs; "
          f"{B} — {sizes[2]:,} titles / {sizes[3]:,} DOIs.)*")
        w()
        for ck, short in (("a", A), ("b", B)):
            c = counts[ck]
            tot = c["internal"] + c["external"] + c["other"] or 1
            other_short = B if ck == "a" else A
            w(f"### References made by {short} papers")
            w()
            w(f"| Target | References | % |")
            w(f"|---|---:|---:|")
            w(f"| Internal (→ {short}, any year) | {c['internal']:,} | "
              f"{c['internal']/tot*100:.1f}% |")
            w(f"| External (→ {other_short}, any year) | {c['external']:,} | "
              f"{c['external']/tot*100:.1f}% |")
            w(f"| Other (neither) | {c['other']:,} | {c['other']/tot*100:.1f}% |")
            w(f"| **Total** | **{tot:,}** | 100% |")
            w()
            if c["external"]:
                w(f"- Internal-to-external ratio: {c['internal']/c['external']:.1f} "
                  f"({short} cites its own community "
                  f"{c['internal']/c['external']:.1f}× more than the other)")
            w()
        ext_a, ext_b = counts["a"]["external"], counts["b"]["external"]
        w("### Cross-community comparison (all years)")
        w()
        w(f"- {A} → {B} references: {ext_a:,}")
        w(f"- {B} → {A} references: {ext_b:,}")
        if ext_a and ext_b:
            w(f"- Asymmetry ratio ({A}→{B} : {B}→{A}): {ext_a/ext_b:.2f}")
        w()
        w("*Note: the two reference lists may differ in coverage (e.g. one "
          "spans an entire anthology, the other a fixed set of venues), so the "
          "'internal' share is more complete for the better-covered community. "
          "The cross-community asymmetry is unaffected by this.*")
        w()

    # ---------- per-venue breakdown ----------
    w("## Per-venue breakdown")
    w()
    venue_papers = Counter(p["venue"] for p in papers.values())
    venue_out = defaultdict(int)   # citations originating from this venue
    venue_cross_out = defaultdict(int)  # cross-cluster citations from this venue
    for src, tgts in citations.items():
        sv = papers[src]["venue"]
        sc = papers[src]["cluster"]
        for t in tgts:
            venue_out[sv] += 1
            if papers[t]["cluster"] != sc:
                venue_cross_out[sv] += 1
    w(f"| Venue | Cluster | Papers | Citations made | Cross-cluster citations made |")
    w(f"|---|---|---:|---:|---:|")
    for v in a.venues + b.venues:
        cl = A if v in a.venues else B
        w(f"| {v.upper()} | {cl} | {venue_papers.get(v,0):,} | "
          f"{venue_out.get(v,0):,} | {venue_cross_out.get(v,0):,} |")
    w()

    # ---------- bridge venues ----------
    w("## Bridge venues (most cross-community citations)")
    w()
    w("Venues ranked by how many cross-community citations their papers make "
      "(outgoing) — candidates for 'bridges' between the two fields.")
    w()
    bridges = sorted(venue_cross_out.items(), key=lambda kv: -kv[1])[:10]
    w(f"| Venue | Cross-cluster citations made |")
    w(f"|---|---:|")
    for v, n in bridges:
        w(f"| {v.upper()} | {n:,} |")
    w()

    # ---------- top countries per cluster ----------
    def top_countries(cluster_key, n=20):
        cnt = Counter()
        for pid, p in papers.items():
            if p["cluster"] != cluster_key:
                continue
            for c in set(affil.get(pid, {}).get("countries", [])):
                cnt[c] += 1
        return cnt.most_common(n)

    for ck, short in (("a", A), ("b", B)):
        w(f"## Top countries — {short}")
        w()
        w(f"| Rank | Country | Papers |")
        w(f"|---:|---|---:|")
        for i, (c, n) in enumerate(top_countries(ck), 1):
            w(f"| {i} | {cname(c)} ({c}) | {n:,} |")
        w()

    # ---------- top institutions per cluster ----------
    def top_institutions(cluster_key, n=20):
        cnt = Counter()
        for pid, p in papers.items():
            if p["cluster"] != cluster_key:
                continue
            for inst in affil.get(pid, {}).get("institutions", []):
                cnt[inst] += 1
        return cnt.most_common(n)

    for ck, short in (("a", A), ("b", B)):
        w(f"## Top institutions — {short}")
        w()
        w(f"| Rank | Institution | Papers |")
        w(f"|---:|---|---:|")
        for i, (inst, n) in enumerate(top_institutions(ck), 1):
            w(f"| {i} | {inst} | {n:,} |")
        w()

    # ---------- top co-authoring country pairs ----------
    w("## Top co-authoring country pairs")
    w()
    w("Pairs of countries that most often appear together on the same paper "
      "(international collaboration).")
    w()
    pairs = sorted(geo["country_pairs"].items(), key=lambda kv: -kv[1])[:20]
    w(f"| Rank | Country pair | Papers |")
    w(f"|---:|---|---:|")
    for i, (key, n) in enumerate(pairs, 1):
        c1, c2 = key.split("|")
        w(f"| {i} | {cname(c1)} – {cname(c2)} | {n:,} |")
    w()

    # ---------- most-cited papers (bridges at paper level) ----------
    w("## Most-cited papers within the corpus")
    w()
    w("Top papers by total in-corpus citations, with how many come from the "
      "*other* community (cross-community incoming).")
    w()
    ranked = sorted(papers, key=lambda pid: -(stats[pid]["ii"] + stats[pid]["ie"]))[:25]
    w(f"| Rank | Cluster | Venue | In-cites (total) | of which cross | Title |")
    w(f"|---:|---|---|---:|---:|---|")
    for i, pid in enumerate(ranked, 1):
        p = papers[pid]
        st = stats[pid]
        total_in = st["ii"] + st["ie"]
        cl = A if p["cluster"] == "a" else B
        title = p["title"][:70].replace("|", "/")
        w(f"| {i} | {cl} | {p['venue'].upper()} | {total_in} | {st['ie']} | {title} |")
    w()

    out = Path(args.out)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
