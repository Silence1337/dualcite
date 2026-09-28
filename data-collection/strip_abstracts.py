"""
strip_abstracts.py: remove the abstracts from the GROBID header XML files before
they are published. DualCite reads only authors and affiliations from these
files, and abstracts of papers published under a publisher's copyright should
not be redistributed. The rest of each file is left byte-for-byte unchanged.

Run from the repository root:

    python data-collection/strip_abstracts.py data/headers_xml
"""
import re
import sys
from pathlib import Path

ABSTRACT = re.compile(r"<abstract\b[^>]*/>|<abstract\b[^>]*>.*?</abstract>", re.S)


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/headers_xml")
    files = sorted(root.rglob("*.xml"))
    changed = saved = 0
    for f in files:
        text = f.read_text("utf-8")
        new, n = ABSTRACT.subn("", text)
        if n:
            f.write_text(new, "utf-8")
            changed += 1
            saved += len(text.encode("utf-8")) - len(new.encode("utf-8"))
    print(f"{len(files):,} header files, abstracts removed from {changed:,}, {saved / 1e6:.1f} MB smaller")


if __name__ == "__main__":
    main()
