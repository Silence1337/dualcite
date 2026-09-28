"""
grobid_runner.py: run PDFs through a local GROBID server.

Produces the two XML sets DualCite needs:
  - references (processReferences)  -> refs_xml/
  - headers    (processHeaderDocument, for affiliations) -> headers_xml/

GROBID must be running locally. The easiest way:

    docker run --rm -p 8070:8070 grobid/grobid:0.8.2-crf

Usage:
    python -m dualcite.grobid_runner ./my_pdfs --config config.yaml
    python -m dualcite.grobid_runner ./my_pdfs --refs-only
    python -m dualcite.grobid_runner ./my_pdfs --headers-only

Both passes are resumable: already-processed PDFs are skipped, so you can
re-run after an interruption.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

from .config import load_config

REFS_ENDPOINT = "/api/processReferences"
HEADER_ENDPOINT = "/api/processHeaderDocument"


def _check_alive(url: str):
    try:
        r = requests.get(f"{url}/api/isalive", timeout=5)
        if r.status_code == 200:
            return True
    except Exception:
        pass
    return False


def _process(pdf_dir: Path, out_dir: Path, endpoint: str, url: str,
             delay: float, label: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"  No PDFs found in {pdf_dir}", file=sys.stderr)
        return
    done = {p.stem for p in out_dir.glob("*.xml")}
    todo = [p for p in pdfs if p.stem not in done]
    print(f"[{label}] {len(pdfs)} PDFs, {len(done)} done, "
          f"{len(todo)} to process", file=sys.stderr)

    failed = []
    full = f"{url}{endpoint}"
    for i, pdf in enumerate(todo):
        if i % 50 == 0:
            print(f"  {label}: {i}/{len(todo)}\r", file=sys.stderr, end="")
        ok = False
        for attempt in range(3):          # retry when the server is busy or slow
            try:
                with open(pdf, "rb") as f:
                    resp = requests.post(
                        full,
                        files={"input": (pdf.name, f, "application/pdf")},
                        headers={"Accept": "application/xml"},  # force TEI, not BibTeX
                        timeout=120)
                if resp.status_code == 200 and resp.content.lstrip()[:1] == b"<":
                    (out_dir / f"{pdf.stem}.xml").write_bytes(resp.content)
                    ok = True
                    break
                if resp.status_code != 503:
                    break                   # a real error: retrying will not help
            except requests.RequestException:
                pass
            time.sleep(5 * (attempt + 1))
        if not ok:
            failed.append(pdf.name)
        time.sleep(delay)
    print(f"  {label}: done ({len(failed)} errors)          ", file=sys.stderr)
    if failed:
        report = Path(f"grobid_failed_{out_dir.parent.name}_{out_dir.name}.txt")
        report.write_text("\n".join(failed) + "\n", "utf-8")
        print(f"  files that failed are listed in {report}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Run PDFs through GROBID")
    ap.add_argument("pdf_dir", help="Directory containing PDF files")
    ap.add_argument("--cluster", required=True, choices=["a", "b"],
                    help="Which cluster these PDFs belong to (a or b). "
                         "Output XML goes to the matching cluster subfolder.")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--grobid-url", default="http://localhost:8070")
    ap.add_argument("--delay", type=float, default=0.1)
    ap.add_argument("--refs-only", action="store_true")
    ap.add_argument("--headers-only", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        sys.exit(f"PDF directory not found: {pdf_dir}")

    if not _check_alive(args.grobid_url):
        sys.exit(f"GROBID not reachable at {args.grobid_url}\n"
                 f"Start it with:\n"
                 f"  docker run --rm -p 8070:8070 grobid/grobid:0.8.2-crf")

    ck = args.cluster
    if not args.headers_only:
        _process(pdf_dir, cfg.path("refs_xml") / ck, REFS_ENDPOINT,
                 args.grobid_url, args.delay, f"references [{ck}]")
    if not args.refs_only:
        _process(pdf_dir, cfg.path("headers_xml") / ck, HEADER_ENDPOINT,
                 args.grobid_url, args.delay, f"headers [{ck}]")

    print("\nDone. Next: python -m dualcite.app --config", args.config,
          file=sys.stderr)


if __name__ == "__main__":
    main()
