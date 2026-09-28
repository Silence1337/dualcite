"""
make_flagship_lists.py: historical publication lists of the two flagship
conferences, used by config_acl_sigir.yaml (thesis Section 6.5.5).

  acl    All papers of the main ACL conference, 1979 onward, taken from the full
         ACL Anthology list and recognized by their ids: P79-1001 ... P19-5010
         (letter P = ACL) and 2020.acl-main.12, 2025.acl-long.1, ...
         Findings, workshops and the journal are left out.
         Input:  reference-lists/acl_all_papers_full.json
         Output: reference-lists/acl_main_all_years.json

  sigir  All papers of the main SIGIR conference available in the ACM Digital
         Library, collected from Crossref (proceedings named "... ACM SIGIR
         Conference on Research and Development in Information Retrieval";
         SIGIR-AP, ICTIR, CHIIR, workshops and the SIGIR Forum are left out).
         Output: reference-lists/sigir_main_all_years.json

Run from the repository root:

    python data-collection/make_flagship_lists.py acl
    python data-collection/make_flagship_lists.py sigir --email you@example.com

Afterwards compress the outputs (gzip -k) to match the published files.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_ir_crossref import collect_volumes, dedupe  # noqa: E402

ACL_IN = Path("reference-lists/acl_all_papers_full.json")
ACL_OUT = Path("reference-lists/acl_main_all_years.json")
SIGIR_OUT = Path("reference-lists/sigir_main_all_years.json")

ACL_MAIN_ID = re.compile(r"(?:^|[/\s])(P\d\d-\d{4}|\d{4}\.acl-(?:main|long|short|demo|demos|industry|srw|tutorials?)\.\d+)(?:\.pdf)?(?:$|[/\s])")
SIGIR_EXCLUDE = ("asia pacific", "forum", "innovative concepts", "theory of information retrieval",
                 "human information interaction", "workshop", "companion")


def strings(entry):
    """All string values of an entry, including nested ones."""
    if isinstance(entry, str):
        yield entry
    elif isinstance(entry, dict):
        for v in entry.values():
            yield from strings(v)
    elif isinstance(entry, list):
        for v in entry:
            yield from strings(v)


def acl_main_id(entry):
    for s in strings(entry):
        m = ACL_MAIN_ID.search(s.strip())
        if m:
            return m.group(1)
    return None


def sigir_main(title, year):
    """Proceedings volume of the main SIGIR conference (all eras of its name)."""
    t = title.lower()
    named = "research and development in information retrieval" in t or "acm sigir conference" in t
    return named and not any(x in t for x in SIGIR_EXCLUDE)


def make_acl():
    data = json.loads(ACL_IN.read_text("utf-8"))
    acl = [e for e in data if acl_main_id(e)]
    ACL_OUT.write_text(json.dumps(acl, ensure_ascii=False), "utf-8")
    by = Counter(acl_main_id(e)[1:3] if acl_main_id(e).startswith("P") else acl_main_id(e)[:4] for e in acl)
    print(f"ACL main, all years: {len(acl):,} entries -> {ACL_OUT}")
    print("   by id year:", dict(sorted(by.items())))


def make_sigir(email):
    print("SIGIR main conference, all years (ACM), proceedings volumes:")
    recs = []
    for q in ("SIGIR Conference on Research and Development in Information Retrieval",
              "annual international ACM SIGIR conference research development information retrieval"):
        recs += collect_volumes("10.1145", q, sigir_main, "SIGIR", email)
    recs = dedupe(recs)
    SIGIR_OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1), "utf-8")
    years = Counter(r["year"] for r in recs)
    print(f"SIGIR main, all years: {len(recs):,} entries -> {SIGIR_OUT}")
    print("   by year:", dict(sorted((y or 0, n) for y, n in years.items())))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", choices=["acl", "sigir"])
    ap.add_argument("--email", help="contact e-mail for the Crossref polite pool (sigir only)")
    args = ap.parse_args()
    make_acl() if args.which == "acl" else make_sigir(args.email)


if __name__ == "__main__":
    main()
