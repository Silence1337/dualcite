# Historical publication lists

These lists contain the papers of each community in all years. `export_summary.py`
uses them for the reference-list measurement: every reference of a 2025 paper is
classified as internal, external, or other by matching it against the two lists
(DOI and exact normalized title).

| File | Entries | Content | Used by |
|---|---:|---|---|
| `acl_all_papers_full.json.gz` | 121,685 | The whole ACL Anthology, 1952 onward, including workshops and journals | `config.yaml` (CL) |
| `ir_all_years_works.json.gz` | 36,588 | ECIR, CIKM, WWW and the other ACM-published IR conferences, 1993 onward | `config.yaml` (IR) |
| `acl_main_all_years.json.gz` | 13,466 | Main ACL conference only, 1979 onward | `config_acl_sigir.yaml` |
| `sigir_main_all_years.json.gz` | 7,993 | Main SIGIR conference, all years available in the ACM Digital Library | `config_acl_sigir.yaml` |

The files are stored compressed. `export_summary.py` reads the `.json.gz` file
automatically when it is given the `.json` name, so the commands in the main
README work without unpacking anything.

Each file is a JSON list of records with at least a `title` field; a `doi` field
is used when present. How each list was built is described in
`../data-collection/README.md`. Without these files, `export_summary.py` still
runs and only omits the reference-list section.
