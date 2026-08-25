# DualCite

**Interactive visualization of citation flows and author geography between two
groups of academic venues.**

DualCite takes two sets of conferences — say, Computational Linguistics venues
and Information Retrieval venues — and lets you explore, in the browser, how
much they cite each other and where their authors are based. It ships with a
2025 CL vs IR dataset as a working example, but works for **any** two venue
groups you configure.

Two views, one app:

- **Citation Graph** — every paper is a node, sized by how often it's cited
  within the corpus; edges are coloured by direction (within-group vs
  cross-group), so cross-community citation flow is visible at a glance.
- **Geo Map** — a world choropleth of author affiliations, filterable by venue,
  with per-country detail (venue breakdown, top institutions, co-authoring
  countries, most-cited papers).

Selecting conferences in the shared sidebar applies to both views at once.

### Citation Graph
*Papers as nodes (sized by in-corpus citations), edges coloured by direction —
within-community versus cross-community citation flow at a glance.*

![Citation graph view](examples/screenshots/graph.png)

### Geo Map
*World choropleth of author affiliations, filterable by venue, with per-country
detail on click.*

![Geo map view](examples/screenshots/geomap.png)

---

## Quickstart (with the bundled example data)

```bash
git clone https://github.com/Silence1337/dualcite.git
cd dualcite
pip install -r requirements.txt
python -m dualcite.app
```

The browser opens at `http://127.0.0.1:8050`. The first run builds a
precomputed index from the bundled data and caches it; later runs start
instantly.

---

## Using your own data

DualCite reads two things:

1. **Two paper-list JSON files** (one per group), with each paper's id, venue,
   title, and DOI.
2. **GROBID XML** for those papers — references (for the citation graph) and
   headers (for affiliations).

### Step 1 — Get the paper lists

Produce two JSON files, e.g. `data/papers/cluster_a.json` and `cluster_b.json`.
Each is a list of objects. The field names are up to you — you map them in
`config.yaml`. Example:

```json
[
  {"anthology_id": "2025.acl-long.1", "venue": "acl",
   "title": "Some Paper", "doi": "10.18653/v1/2025.acl-long.1"}
]
```

The `data-collection/` folder has the (source-specific) scripts we used to build
the example corpus — treat them as a reference, not a turnkey tool.

### Step 2 — Download the PDFs

Put each cluster's PDFs into the folders provided for them: `pdfs/a` for cluster
A and `pdfs/b` for cluster B.

How you fill them depends on your sources. CL venues (ACL Anthology) are open
access and download directly; most IR venues (ACM) are paywalled and need
institutional access. The `data-collection/` scripts (`download_acl.py`,
`download_ir.py`) show how we did it for the example corpus — see
`data-collection/README.md`, including the legal note on paywalled sources. If
you already have the PDFs, just drop them into `pdfs/a` and `pdfs/b`.

The PDF filenames must match the paper ids the tool expects: for cluster A the
id itself (e.g. `2025.acl-long.1.pdf`), for cluster B `{sanitized_title}__{doi_suffix}.pdf`.
The download scripts handle this naming automatically.

### Step 3 — Run the PDFs through GROBID

[GROBID](https://github.com/kermitt2/grobid) is an open-source tool that parses
scholarly PDFs into structured XML. DualCite uses it to pull two things out of
each paper: its reference list (for the citation graph) and its author
affiliations (for the geo map). It runs as a local server that the tool sends
PDFs to. The easiest way to start one is Docker:

```bash
docker run --rm -p 8070:8070 lfoppiano/grobid:0.8.1
```

Then run each cluster's PDFs separately, telling the runner which cluster they
belong to (`a` or `b`):

```bash
python -m dualcite.grobid_runner ./pdfs/a --cluster a --config config.yaml
python -m dualcite.grobid_runner ./pdfs/b --cluster b --config config.yaml
```

This produces per-cluster subfolders:

```
data/refs_xml/a/     data/refs_xml/b/
data/headers_xml/a/  data/headers_xml/b/
```

It's resumable — if interrupted, just run it again and it skips what's done.

### Step 4 — Configure

Edit `config.yaml` to describe your two groups. Everything venue-specific lives
here — cluster names, colours, which venues belong to which group, how to read
your JSON fields, and how to recognise a venue from a citation string. See the
comments in `config.yaml`.

### Step 5 — Launch

```bash
python -m dualcite.app --config config.yaml
```

To rebuild the index after changing data or config, delete
`data/.precomputed/index.json` (or it rebuilds automatically when the config
version changes).

---

## How it works

```
PDFs ──GROBID──> refs_xml/{a,b}/     ─┐
                 headers_xml/{a,b}/  ─┤
                                      ├──> build_index ──> .precomputed/index.json
paper JSONs ──────────────────────────┘         │
                                          ├─ citation matching (DOI + fuzzy title)
                                          ├─ affiliation parsing (country, institution)
                                          └─ flow aggregation (a→a, a→b, b→a, b→b)
                                                     │
                                        ┌────────────┴────────────┐
                                   Citation Graph            Geo Map
```

**Citation matching.** Most reference strings extracted from PDFs have no DOI, so
matching relies on normalised-title comparison with fuzzy fallback (rapidfuzz).
A citation counts as intra-corpus only when its target resolves to another paper
in the corpus.

**Speed.** Everything expensive is computed once and cached. Changing venue
filters just re-aggregates precomputed counts, so both views stay responsive
even on large corpora.

---

## Tuning the configuration

`config.yaml` holds more than just the venue lists — it controls how papers are
classified, and the defaults won't be perfect for every corpus. If the results
don't look right, this is the first place to adjust. A few things to know:

- **Venue patterns** (`venue_patterns`) decide which venue a paper or a citation
  belongs to, by matching substrings against a free-text source string. Order
  matters: more specific patterns must come before more general ones, because
  the first match wins. If papers land in the wrong venue — or a whole venue
  looks emptier than expected — check whether its patterns are too narrow, or
  whether a broader pattern above it is catching them first. (For example, a
  CHIIR proceedings title contains the substring "sigir", so the chiir pattern
  is deliberately listed before the bare "sigir" one.)

- **Field schema** (`schema`) maps your JSON fields to what the tool expects.
  If a cluster comes up nearly empty, the field names here probably don't match
  your data. The tool tries a direct venue field first, then falls back to
  matching the free-text field via the patterns above — so a paper can be
  classified from either.

- **Fuzzy matching** (`matching.fuzzy_threshold`, `min_words_for_fuzzy`) controls
  how citations are linked to corpus papers when they have no DOI. A higher
  threshold means stricter title matching: fewer false links, but more real
  citations missed. Lower it if too few citations are being found; raise it if
  unrelated papers are being linked.

Because all of this is heuristic, some rows will inevitably be misclassified —
a citation matched to the wrong paper, a venue or country guessed incorrectly.
The console prints coverage and match statistics when the index is built; those
numbers are the quickest way to see whether a config change helped. After any
change to `config.yaml` or the data, delete `data/.precomputed/index.json` to
force a rebuild.

---

## Limitations (worth knowing)

- **GROBID coverage isn't 100%.** Some references and affiliations won't be
  extracted, especially from unusual PDF layouts. Coverage numbers are printed
  when the index is built.
- **Affiliation counting is "full counting"** — a paper with authors from N
  countries counts once for each. Country totals therefore sum to more than the
  paper count.
- **Venue and country classification is heuristic.** Venues are matched from
  free-text strings and paper ids; countries are inferred from affiliation tags
  and, where those are missing, from institution names. Both can misclassify
  edge cases — see "Tuning the configuration" above.
- **The data-collection scripts are research code**, specific to our sources —
  see `data-collection/README.md`.

---

## Repository layout

```
dualcite/
├── config.yaml            # everything venue-specific lives here
├── dualcite/              # the tool
│   ├── app.py             # unified app with tabs
│   ├── config.py          # config loading/validation
│   ├── index.py           # data loading, matching, index building
│   ├── grobid_runner.py   # PDF → XML
│   └── tabs/
│       ├── graph.py       # citation graph
│       └── geomap.py       # geo map
├── data/                  # bundled 2025 CL vs IR example data
│   ├── papers/            #   cluster_a.json, cluster_b.json
│   ├── refs_xml/{a,b}/    #   references per cluster
│   └── headers_xml/{a,b}/ #   headers per cluster
├── pdfs/{a,b}/            # put your own PDFs here (empty by default)
├── data-collection/       # research scripts used to build that data
├── examples/screenshots/  # screenshots shown in this README
└── requirements.txt
```

## License

MIT — see [LICENSE](LICENSE).
