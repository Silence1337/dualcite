# Data collection scripts

**These are research scripts, not part of the DualCite tool.** They document how
the bundled 2025 IR + CL corpus was assembled, and are provided for
reproducibility and as a starting point if you want to build your own corpus.

They are **specific to our sources** (ACL Anthology, DBLP, the ACM Digital
Library) and contain hard-coded venue lists, years, and endpoints. They are not
a general, configurable pipeline the way the main tool is. Expect to edit them.

## What each script does

| Script | Purpose |
|---|---|
| `collect_acl_2025.py`, `collect_all_acl_articles.py` | Pull the 2025 paper list from the ACL Anthology (open, well-structured API). |
| `collect_all_acm.py`, `collect_all_CIKM.py`, `collect_all_ecir.py` | Pull IR paper lists from DBLP / Crossref for the ACM-published venues. |
| `merge_ir_sources.py`, `filter_IR_2025_works.py` | Merge and filter the IR lists into a single cleaned set. |
| `download_acl.py` | Download CL PDFs. ACL Anthology is fully open access — works for anyone, no credentials. |
| `download_ir.py` | Download IR PDFs. See the legal note below. |

The output of the collection step is the two paper-list JSON files the main tool
reads (`data/papers/cluster_a.json`, `cluster_b.json`).

## Legal note on IR PDFs

CL venues (ACL Anthology) are open access — `download_acl.py` downloads them
directly and works for everyone.

Most IR venues (SIGIR, CIKM, WWW, WSDM) are published by the **ACM** and sit
behind a paywall. The **ACM Digital Library prohibits automated/bulk
downloading.** `download_ir.py` offers two paths:

1. **Open-access copies** (Unpaywall, OpenAlex, arXiv) — legal for anyone, but
   covers only papers with an OA version, so coverage is partial.
2. **ACM via an authenticated browser** (`--acm`, uses Playwright) — opens a
   real browser window that **you** log into with **your own institutional
   credentials**, then automates clicks in a session you are personally
   authorised to use.

You are responsible for complying with the ACM's terms of service and your
institution's license agreement. If in doubt, download manually.

An earlier version of this script used Sci-Hub as a fallback. **It has been
removed and should not be restored.** Use only sources you are entitled to
access.

## Then what

Once you have PDFs, leave these scripts behind and use the main tool:

```bash
# 1. run each cluster's PDFs through GROBID (needs a local GROBID server)
python -m dualcite.grobid_runner ./cluster_a_pdfs --cluster a --config config.yaml
python -m dualcite.grobid_runner ./cluster_b_pdfs --cluster b --config config.yaml

# 2. launch
python -m dualcite.app --config config.yaml
```
