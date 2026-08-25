"""
download_ir.py — download PDFs for IR-cluster papers.

RESEARCH CODE — specific to how our 2025 IR corpus was assembled. Kept for
reproducibility, not as a general-purpose downloader. Adapt to your sources.

Source order (first hit wins):
  1. ACM Digital Library via an authenticated browser (Playwright)
  2. Unpaywall / OpenAlex / Semantic Scholar / arXiv open-access copies

IMPORTANT — legal note:
  Most IR venues (SIGIR, CIKM, WWW, WSDM) are published by the ACM and sit
  behind a paywall. The ACM Digital Library PROHIBITS automated/bulk
  downloading. The Playwright path below opens a real browser window that you
  log into with your own institutional credentials; it automates clicks in a
  session you are personally authorised to use. You are responsible for
  complying with the ACM's terms and your institution's license. If in doubt,
  download manually or use only the open-access sources.

  (An earlier version of this script also tried Sci-Hub as a last resort. That
  has been removed — do not restore it. Use only sources you are entitled to.)

Requirements:
  pip install requests playwright
  playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def sanitize_title(t: str, n: int = 80) -> str:
    s = re.sub(r"[^\w\s-]", "", t)[:n].strip()
    return re.sub(r"\s+", "_", s)


def doi_suffix(d: str) -> str:
    return d.rsplit("/", 1)[-1] if d else "unknown"


def out_name(paper: dict) -> str:
    """Filename stem: sanitize(title)__doi_suffix — matches the analysis side."""
    return f"{sanitize_title(paper.get('title',''))}__{doi_suffix(paper.get('doi',''))}"


# ─────────────────────────── open-access sources ───────────────────────────

def try_unpaywall(session, doi, email):
    if not doi:
        return None
    try:
        r = session.get(f"https://api.unpaywall.org/v2/{doi}",
                        params={"email": email}, timeout=20)
        if r.status_code == 200:
            loc = (r.json() or {}).get("best_oa_location") or {}
            url = loc.get("url_for_pdf")
            if url:
                pdf = session.get(url, timeout=40)
                if pdf.status_code == 200 and pdf.content[:4] == b"%PDF":
                    return pdf.content
    except Exception:
        pass
    return None


def try_openalex(session, doi):
    if not doi:
        return None
    try:
        r = session.get(f"https://api.openalex.org/works/https://doi.org/{doi}",
                        timeout=20)
        if r.status_code == 200:
            loc = (r.json() or {}).get("best_oa_location") or {}
            url = loc.get("pdf_url")
            if url:
                pdf = session.get(url, timeout=40)
                if pdf.status_code == 200 and pdf.content[:4] == b"%PDF":
                    return pdf.content
    except Exception:
        pass
    return None


def try_arxiv(session, title):
    if not title:
        return None
    try:
        q = requests.utils.quote(f'ti:"{title}"')
        r = session.get(
            f"http://export.arxiv.org/api/query?search_query={q}&max_results=1",
            timeout=20)
        if r.status_code == 200:
            m = re.search(r"<id>(http://arxiv\.org/abs/[^<]+)</id>", r.text)
            if m:
                pdf_url = m.group(1).replace("/abs/", "/pdf/") + ".pdf"
                pdf = session.get(pdf_url, timeout=40)
                if pdf.status_code == 200 and pdf.content[:4] == b"%PDF":
                    return pdf.content
    except Exception:
        pass
    return None


# ─────────────────────────── ACM via Playwright ───────────────────────────

def try_acm_playwright(pw_page, doi, out_path):
    """
    Navigate to the ACM DL page for a DOI in an authenticated browser and click
    the PDF download. Requires you to have logged in (institutional access) in
    the browser window that Playwright opened.
    """
    if not doi or pw_page is None:
        return None
    try:
        pw_page.goto(f"https://dl.acm.org/doi/{doi}", timeout=45000)
        pw_page.wait_for_timeout(2000)
        # try the PDF link/button (selector may need adjusting for ACM changes)
        for sel in ['a[title="PDF"]', 'a.btn--pdf', 'a[href*="/doi/pdf/"]']:
            el = pw_page.query_selector(sel)
            if el:
                href = el.get_attribute("href")
                if href:
                    if href.startswith("/"):
                        href = "https://dl.acm.org" + href
                    # download via the page's authenticated context
                    resp = pw_page.context.request.get(href, timeout=45000)
                    body = resp.body()
                    if body[:4] == b"%PDF":
                        return body
    except Exception:
        pass
    return None


def build_sources(email, use_acm, pw_page):
    sources = []
    if use_acm:
        sources.append(("ACM (browser)",
                        lambda s, p: try_acm_playwright(pw_page, p.get("doi"),
                                                        None)))
    sources += [
        ("Unpaywall",  lambda s, p: try_unpaywall(s, p.get("doi"), email)),
        ("OpenAlex",   lambda s, p: try_openalex(s, p.get("doi"))),
        ("arXiv",      lambda s, p: try_arxiv(s, p.get("title"))),
    ]
    return sources


def main():
    ap = argparse.ArgumentParser(description="Download IR-cluster PDFs")
    ap.add_argument("json_file", help="JSON list of IR papers (title, doi, ...)")
    ap.add_argument("--out", default="ir_pdfs", help="Output directory")
    ap.add_argument("--email", default="you@example.com",
                    help="Contact email for Unpaywall API")
    ap.add_argument("--acm", action="store_true",
                    help="Enable ACM download via authenticated browser "
                         "(opens a window you must log into)")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    papers = json.loads(Path(args.json_file).read_text("utf-8"))
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)

    pw_page = None
    pw_ctx = None
    if args.acm:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            sys.exit("Playwright required for --acm:  pip install playwright && "
                     "playwright install chromium")
        pw_ctx = sync_playwright().start()
        browser = pw_ctx.chromium.launch(headless=False)
        page_ctx = browser.new_context(user_agent=UA)
        pw_page = page_ctx.new_page()
        print("\n>>> A browser window opened. Log in to your institution's ACM\n"
              ">>> access, then press Enter here to continue...\n")
        input()

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    sources = build_sources(args.email, args.acm, pw_page)

    got = skipped = failed = 0
    for i, p in enumerate(papers, 1):
        stem = out_name(p)
        path = out_dir / f"{stem}.pdf"
        if path.exists():
            skipped += 1
            continue
        content = None
        for name, fn in sources:
            content = fn(session, p)
            if content:
                path.write_bytes(content)
                got += 1
                print(f"[{i}/{len(papers)}] {name}: {stem[:50]}")
                break
        if not content:
            failed += 1
        time.sleep(args.delay)

    print(f"\nDone. {got} downloaded, {skipped} already present, {failed} failed")
    if pw_ctx:
        pw_ctx.stop()


if __name__ == "__main__":
    main()
