# Reference lists (all years)

This folder is for the **all-years reference lists** used by the optional
internal/external/other breakdown in `export_summary.py`:

```bash
python export_summary.py --cl-refs reference-lists/acl_all_papers_full.json \
                         --ir-refs reference-lists/ir_all_years_works.json
```

Each file is a JSON list of objects with at least a `title` field (a `doi` field
is used too when present) — one entry per paper published at that community's
venues, across all years.

## Why they aren't in the repository

These lists are large (the ACL Anthology list is ~90 MB) and are intermediate
data, not code or results. They are git-ignored. Generate them yourself, or
drop your own here.

## How to build them

Use the collectors in `../data-collection/`:

- `collect_all_acl_articles.py` → the full ACL Anthology list (cluster A)
- `collect_all_CIKM.py`, `collect_all_ecir.py`, etc. + `merge_ir_sources.py`
  → the IR list (cluster B)

The exact venues and sources are specific to our corpus; adapt as needed.
Without these files, `export_summary.py` still runs — it just omits the
all-years section.
