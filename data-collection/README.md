# Data collection (research code)

These scripts built the case-study dataset of the thesis: papers published in
2025 at Computational Linguistics (CL) and Information Retrieval (IR)
conferences. They are specific to these venues and data sources and are **not
part of the DualCite tool**, which only needs paper lists and GROBID XML (see the
main README). They are kept so that the dataset can be traced and rebuilt.

Run them from the repository root. Most scripts write their output to the
working directory; the final files belong in the places given below.

## 1. CL papers (cluster A)

| Step | Script | Output |
|---|---|---|
| 2025 paper list | `collect_acl_2025.py` | `acl_papers_2025.json` → `data/papers/cluster_a.json` |
| PDFs | `download_acl.py` | `acl_pdfs_2025/` |

`collect_acl_2025.py` reads the ACL Anthology (`pip install acl-anthology`) and
takes all volumes of the 2025 ACL, EMNLP, NAACL, COLING, IJCNLP, LREC and EACL
events, including Findings and co-located workshops. The records that describe a
whole volume (front matter) are left out later by the exclusion rules of
`config.yaml`.

## 2. IR papers (cluster B)

| Step | Script | Output |
|---|---|---|
| ACM IR conferences, all years | `collect_acm_ir_all_years.py` | `acm_ir_all_years.json` |
| ECIR, all years | `collect_ecir_all_years.py` | `ecir_all_years_works.json` |
| CIKM, all years | `collect_cikm_all_years.py` | `cikm_all_years_works.json` |
| Merge | `merge_ir_sources.py` | `ir_all_years_works.json` |
| 2025 papers | `filter_ir_2025.py` | `ir_2025_works.json` → `data/papers/cluster_b.json` |
| WWW and ECIR 2025 | `collect_ir_crossref.py papers --merge data/papers/cluster_b.json` | added to `cluster_b.json` |
| PDFs | `download_ir.py` | one folder of PDFs |

The first collectors missed two venues. The keywords of
`collect_acm_ir_all_years.py` do not match the recent proceedings titles of WWW
("Proceedings of the ACM on Web Conference"), and an early version of the 2025
filter compared the year as a number while dblp returns it as text, which dropped
ECIR. Both were fixed, and the 2025 papers of WWW and ECIR were then collected
directly from Crossref with `collect_ir_crossref.py`, which locates each
proceedings volume and takes all of its papers.

`download_ir.py` needs Playwright (`pip install playwright` and
`playwright install chromium`). It tries the publisher first (ACM Digital Library, SpringerLink)
in a browser window and falls back to open copies (Unpaywall, OpenAlex, arXiv,
accepted only if the title matches). Use it only with access you are entitled to.
The PDFs are not redistributed.

## 3. Historical lists for the reference-list measurement

| List | Script | Published file |
|---|---|---|
| All ACL Anthology papers | `collect_acl_all_years.py` | `reference-lists/acl_all_papers_full.json.gz` |
| IR conferences, all years | steps of section 2 up to the merge, then `collect_ir_crossref.py www-history --merge reference-lists/ir_all_years_works.json` | `reference-lists/ir_all_years_works.json.gz` |
| Main ACL conference | `make_flagship_lists.py acl` | `reference-lists/acl_main_all_years.json.gz` |
| Main SIGIR conference | `make_flagship_lists.py sigir` | `reference-lists/sigir_main_all_years.json.gz` |

The last two lists are used by `config_acl_sigir.yaml`. Compress new outputs with
`gzip -k` to match the published files.

## 4. Before publishing the header XML

```bash
python data-collection/strip_abstracts.py data/headers_xml
```

removes the paper abstracts from the GROBID header files. DualCite reads only
authors and affiliations from them, and the result of the affiliation analysis
does not change.

## Notes

- **dblp** blocks automated requests since 2026, so `collect_ecir_all_years.py`
  and `collect_cikm_all_years.py` may no longer run. `collect_ir_crossref.py`
  uses Crossref instead; pass `--email` to use Crossref's faster "polite" pool.
- **Years from Crossref.** `collect_acm_ir_all_years.py` takes the year from the
  Crossref `created` date, the date of DOI registration, which for older ACM
  papers is often 2003. For papers of 2025, which is what `filter_ir_2025.py`
  selects, registration and publication normally fall in the same year, and the
  reference-list measurement uses only titles and DOIs. `collect_ir_crossref.py`
  and `make_flagship_lists.py` use the publication date.
