"""
export_summary.py: dump all the valuable aggregates from a built DualCite index
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
import gzip
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


def _read_json(path):
    """Read a JSON file, or its gzip-compressed version (path + ".gz") if only
    that exists. The historical lists are published compressed."""
    p = Path(path)
    if not p.exists() and Path(str(p) + ".gz").exists():
        p = Path(str(p) + ".gz")
    if p.suffix == ".gz":
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(p.read_text("utf-8"))


def _load_ref_titles(path):
    """Return (normalized_titles_set, dois_set) from an all-years reference list."""
    data = _read_json(path)
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
    Classify every reference of the corpus papers against the all-years
    reference lists, as internal / external / other. Returns
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
        for title, doi, _ in refs:
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

    Unlike the in-corpus links, which only connect papers of the corpus, this
    counts every reference to a configured venue, whenever the cited work was
    published.

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


def flow_shares(papers, edges):
    """Cross-community shares for a set of (src, tgt) edges."""
    f = {"a_a": 0, "a_b": 0, "b_a": 0, "b_b": 0}
    for s, t in edges:
        f[f"{papers[s]['cluster']}_{papers[t]['cluster']}"] += 1
    a_tot, b_tot = f["a_a"] + f["a_b"], f["b_a"] + f["b_b"]
    return f, (f["a_b"] / a_tot * 100 if a_tot else 0.0), (f["b_a"] / b_tot * 100 if b_tot else 0.0)


def robustness_section(w, cfg, index, A, B):
    papers, log_ = index["papers"], index.get("match_log", [])
    if not log_:
        return
    thr = cfg.fuzzy_threshold

    def edges(cond):
        return {(m[0], m[1]) for m in log_ if cond(m)}
    ok_score = lambda m, t: m[2] != "fuzzy" or m[3] >= t
    scen = [
        (f"Configured rule: DOI + exact + fuzzy >= {thr}, year check", lambda m: m[5] and ok_score(m, thr)),
        ("Same rule without the year check", lambda m: ok_score(m, thr)),
        ("DOI + exact title only (no fuzzy), year check", lambda m: m[5] and m[2] != "fuzzy"),
        ("DOI only", lambda m: m[2] == "doi"),
    ]
    for t in (80, 85, 90, 95):
        scen.append((f"Fuzzy threshold {t}, year check", lambda m, t=t: m[5] and ok_score(m, t)))
    w("## Robustness of the in-corpus citation flow")
    w()
    w("The same flow computed under stricter and looser matching rules. "
      "Shares are the share of each cluster's in-corpus citations that go to the other cluster.")
    w()
    w(f"| Matching rule | Links | {A} -> {B} | {A} -> {B} share | {B} -> {A} | {B} -> {A} share |")
    w("|---|---:|---:|---:|---:|---:|")
    for name, cond in scen:
        es = edges(cond)
        f, sa, sb = flow_shares(papers, es)
        w(f"| {name} | {len(es):,} | {f['a_b']:,} | {sa:.1f}% | {f['b_a']:,} | {sb:.1f}% |")
    w()
    kinds = {k: len(edges(lambda m, k=k: m[2] == k and m[5] and ok_score(m, thr))) for k in ("doi", "exact", "fuzzy")}
    w(f"- Accepted links by match type: DOI {kinds['doi']:,}, exact title {kinds['exact']:,}, fuzzy title {kinds['fuzzy']:,}")
    w(f"- Candidate links rejected by the year check: {len(edges(lambda m: not m[5])):,}")
    w()
    before, after = collections_counter(edges(lambda m: ok_score(m, thr))), collections_counter(edges(lambda m: m[5] and ok_score(m, thr)))
    w("### Most-cited papers before and after the year check")
    w()
    w("| Paper | Cluster | Before | After |")
    w("|---|---|---:|---:|")
    for pid, n in before.most_common(10):
        w(f"| {papers[pid]['title'][:70].replace('|', '/')} | {A if papers[pid]['cluster'] == 'a' else B} | {n:,} | {after.get(pid, 0):,} |")
    w()


def collections_counter(edges):
    c = Counter()
    for _, t in edges:
        c[t] += 1
    return c


def fractional_section(w, index, clusters):
    papers, affil = index["papers"], index["affiliations"]
    w("## Country ranking: full versus fractional counting")
    w()
    w("Full counting gives each country 1 per paper; fractional counting splits each paper equally between its countries.")
    w()
    for ck, short in clusters:
        full, frac = Counter(), Counter()
        for pid, p in papers.items():
            cs = sorted(set(affil.get(pid, {}).get("countries", [])))
            if p["cluster"] != ck or not cs:
                continue
            for c in cs:
                full[c] += 1
                frac[c] += 1 / len(cs)
        rank_full = {c: i + 1 for i, (c, _) in enumerate(full.most_common())}
        w(f"### {short}")
        w()
        w("| Rank (fractional) | Country | Fractional | Full | Rank (full) |")
        w("|---:|---|---:|---:|---:|")
        for i, (c, v) in enumerate(frac.most_common(15), 1):
            w(f"| {i} | {cname(c)} ({c}) | {v:,.1f} | {full[c]:,} | {rank_full[c]} |")
        w()


def affiliation_source_section(w, index):
    affil = index["affiliations"]
    src = Counter(s for a in affil.values() for s in a.get("country_source", {}).values())
    w("## How countries were identified")
    w()
    w("| Source | Paper-country assignments |")
    w("|---|---:|")
    for k in ("key", "text", "address", "inferred"):
        w(f"| {k} | {src.get(k, 0):,} |")
    w()


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

    w("# DualCite results summary")
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
        w("> Most references point to works outside the corpus, such as earlier "
          "papers or papers of other venues. The in-corpus citation flow below "
          "therefore covers only the references that link two papers of the "
          "corpus; its shares are more informative than its absolute counts.")
        w()

    # ---------- citation flows ----------
    w("## Citation flows between the two communities")
    w()
    w("*(Only references that resolve to another paper of the corpus; the "
      "\"other\" references above are excluded.)*")
    w()
    tot = sum(flows.values()) or 1
    w("| Direction | Citations | % of all intra-corpus citations |")
    w("|---|---:|---:|")
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

    # ---------- all years: cited venue names ----------
    w("## References to tracked venues across all years")
    w()
    w("This measurement counts every reference whose cited venue name matches "
      "a configured venue, **whenever the cited work was published**. It "
      "therefore covers far more references than the in-corpus links.")
    w()
    vref, _ = count_venue_references(cfg, index)

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
        w("| Cited venue | Cluster | References |")
        w("|---|---|---:|")
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
        w("## Internal / external / other, matched against all-years lists")
        w()
        w("Every reference of the corpus papers is matched against the all-years "
          f"reference lists of **{A}** and **{B}** and classified as internal "
          "(same community), external (other community), or other (in neither "
          "list). This measurement covers the full history of both communities.")
        w()
        counts, sizes = count_all_years(cfg, index, args.cl_refs, args.ir_refs)
        w(f"*(Reference lists: {A}: {sizes[0]:,} titles / {sizes[1]:,} DOIs; "
          f"{B}: {sizes[2]:,} titles / {sizes[3]:,} DOIs.)*")
        w()
        for ck, short in (("a", A), ("b", B)):
            c = counts[ck]
            tot = c["internal"] + c["external"] + c["other"] or 1
            other_short = B if ck == "a" else A
            w(f"### References made by {short} papers")
            w()
            w("| Target | References | % |")
            w("|---|---:|---:|")
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
    w("| Venue | Cluster | Papers | Citations made | Cross-cluster citations made |")
    w("|---|---|---:|---:|---:|")
    for v in a.venues + b.venues:
        cl = A if v in a.venues else B
        w(f"| {v.upper()} | {cl} | {venue_papers.get(v,0):,} | "
          f"{venue_out.get(v,0):,} | {venue_cross_out.get(v,0):,} |")
    w()

    # ---------- bridge venues ----------
    w("## Bridge venues (most cross-community citations)")
    w()
    w("Venues ranked by the number of cross-community citations their papers make.")
    w()
    bridges = sorted(venue_cross_out.items(), key=lambda kv: -kv[1])[:10]
    w("| Venue | Cross-cluster citations made |")
    w("|---|---:|")
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
        w(f"## Top countries: {short}")
        w()
        w("| Rank | Country | Papers |")
        w("|---:|---|---:|")
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
        w(f"## Top institutions: {short}")
        w()
        w("| Rank | Institution | Papers |")
        w("|---:|---|---:|")
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
    w("| Rank | Country pair | Papers |")
    w("|---:|---|---:|")
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
    w("| Rank | Cluster | Venue | In-cites (total) | of which cross | Title |")
    w("|---:|---|---|---:|---:|---|")
    for i, pid in enumerate(ranked, 1):
        p = papers[pid]
        st = stats[pid]
        total_in = st["ii"] + st["ie"]
        cl = A if p["cluster"] == "a" else B
        title = p["title"][:70].replace("|", "/")
        w(f"| {i} | {cl} | {p['venue'].upper()} | {total_in} | {st['ie']} | {title} |")
    w()

    robustness_section(w, cfg, index, A, B)
    fractional_section(w, index, (("a", A), ("b", B)))
    affiliation_source_section(w, index)

    out = Path(args.out)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {out}  ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
