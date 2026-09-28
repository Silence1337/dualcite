"""
download_ir.py: download PDFs for IR-cluster papers.

RESEARCH CODE: specific to how our 2025 IR corpus was assembled. Kept for
reproducibility, not as a general-purpose downloader. Adapt to your sources.

Source order (first hit wins):
  1. ACM Digital Library via an authenticated browser (Playwright)
  2. Unpaywall / OpenAlex / Semantic Scholar / arXiv open-access copies

IMPORTANT, legal note:
  Most IR venues (SIGIR, CIKM, WWW, WSDM) are published by the ACM and sit
  behind a paywall. The ACM Digital Library PROHIBITS automated/bulk
  downloading. The Playwright path below opens a real browser window that you
  log into with your own institutional credentials; it automates clicks in a
  session you are personally authorised to use. You are responsible for
  complying with the ACM's terms and your institution's license. If in doubt,
  download manually or use only the open-access sources.

  (An earlier version of this script also tried Sci-Hub as a last resort. That
  has been removed, do not restore it. Use only sources you are entitled to.)

Requirements:
  pip install requests playwright
  playwright install chromium
"""
from __future__ import annotations

import argparse
import base64
import difflib
import json
import random
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
    """Filename stem: sanitize(title)__doi_suffix, matches the analysis side."""
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


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())).strip()


def try_arxiv(session, title):
    """arXiv preprint, accepted only if its title matches the paper's title
    (a title search can return a different paper)."""
    if not title:
        return None
    try:
        q = requests.utils.quote(f'ti:"{title}"')
        r = session.get(
            f"http://export.arxiv.org/api/query?search_query={q}&max_results=3",
            timeout=20)
        if r.status_code != 200:
            return None
        for entry in re.findall(r"<entry>(.*?)</entry>", r.text, re.S):
            m_id = re.search(r"<id>(http://arxiv\.org/abs/[^<]+)</id>", entry)
            m_ti = re.search(r"<title>(.*?)</title>", entry, re.S)
            if not (m_id and m_ti):
                continue
            if difflib.SequenceMatcher(None, _norm(m_ti.group(1)), _norm(title)).ratio() < 0.9:
                continue
            pdf_url = m_id.group(1).replace("/abs/", "/pdf/") + ".pdf"
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


def try_publisher(pw_page, doi):
    """
    Download from the publisher in the opened browser window. The browser is
    needed because both sites check for automated clients; the PDF request is
    sent from the page's own session. ACM (DOI prefix 10.1145) has been open
    access since January 2026 and needs no login; Springer (10.1007) needs
    institutional access, so log in to it in the browser window first.
    """
    if not doi or pw_page is None:
        return None
    if doi.startswith("10.1145/"):
        page_url, pdf_url = f"https://dl.acm.org/doi/{doi}", f"https://dl.acm.org/doi/pdf/{doi}"
    elif doi.startswith("10.1007/"):
        page_url, pdf_url = f"https://link.springer.com/chapter/{doi}", f"https://link.springer.com/content/pdf/{doi}.pdf"
    else:
        return None
    try:
        pw_page.goto(page_url, timeout=45000)
        pw_page.wait_for_timeout(1500)
        # 1) fetch from inside the page: carries the browser's cookies and fingerprint
        res = _page_fetch(pw_page, pdf_url)
        body = base64.b64decode(res.get("b64") or "")
        if body[:4] == b"%PDF":
            return body
        # 2) the bot protection may start to challenge background requests. An
        #    ordinary navigation to the PDF passes the check and renews the
        #    browser's clearance, after which the background request works again.
        #    (The PDF viewer itself does not expose the file, so it is fetched once more.)
        resp = pw_page.goto(pdf_url, timeout=60000)
        pw_page.wait_for_timeout(1500)
        pw_page.goto(page_url, timeout=45000)
        pw_page.wait_for_timeout(1000)
        res2 = _page_fetch(pw_page, pdf_url)
        body2 = base64.b64decode(res2.get("b64") or "")
        if body2[:4] == b"%PDF":
            return body2
        _diagnose(doi, res2, resp, body2)
    except Exception as e:
        _diagnose(doi, {"status": "exception", "type": str(e)[:120]}, None, b"")
    return None


def _page_fetch(pw_page, url):
    return pw_page.evaluate("""async (url) => {
        try {
            const r = await fetch(url, {credentials: 'include'});
            const type = r.headers.get('content-type') || '';
            const blob = await r.blob();
            const b64 = await new Promise(res => {
                const fr = new FileReader();
                fr.onloadend = () => res(String(fr.result).split(',')[1] || '');
                fr.readAsDataURL(blob);
            });
            return {status: r.status, type: type, b64: b64};
        } catch (e) { return {status: 0, type: 'error: ' + e, b64: ''}; }
    }""", url)


_DIAG = {"left": 5}


def _diagnose(doi, res, resp, body):
    """Print what the site returned for the first few failed publisher downloads."""
    if _DIAG["left"] <= 0:
        return
    _DIAG["left"] -= 1
    nav = f"{resp.status} {resp.headers.get('content-type', '')}" if resp is not None else "-"
    snippet = body[:120].decode("utf-8", "replace").replace("\n", " ")
    print(f"    [diagnostic {doi}] fetch: {res.get('status')} {res.get('type')}; "
          f"navigation: {nav}; start of response: {snippet!r}")


def build_sources(email, use_acm, pw_page, use_publisher=False):
    sources = []
    if use_publisher:
        sources.append(("publisher (browser)", lambda s, p: try_publisher(pw_page, p.get("doi"))))
    elif use_acm:
        sources.append(("ACM (browser)",
                        lambda s, p: try_acm_playwright(pw_page, p.get("doi"), None)))
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
    ap.add_argument("--publisher", action="store_true",
                    help="Download from the publisher (ACM or Springer, chosen by DOI) in a browser "
                         "window; log in there first if Springer needs institutional access")
    ap.add_argument("--cdp", metavar="URL",
                    help="Connect to an already running Chrome started with "
                         "--remote-debugging-port (e.g. http://localhost:9222) instead of "
                         "launching a new browser")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    papers = json.loads(Path(args.json_file).read_text("utf-8"))
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)

    pw_page = None
    pw_ctx = None
    if args.acm or args.publisher:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            sys.exit("Playwright required for --acm:  pip install playwright && "
                     "playwright install chromium")
        pw_ctx = sync_playwright().start()
        if args.cdp:
            # attach to a normal Chrome window that the user started and logged into
            browser = pw_ctx.chromium.connect_over_cdp(args.cdp)
            page_ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        else:
            browser = pw_ctx.chromium.launch(headless=False)
            page_ctx = browser.new_context(user_agent=UA)
        pw_page = page_ctx.new_page()
        print("\n>>> A browser window opened. ACM needs no login. For Springer, log in there\n"
              ">>> through your institution (link.springer.com, 'Log in via an institution'),\n"
              ">>> then press Enter here to continue...\n")
        input()

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    sources = build_sources(args.email, args.acm, pw_page, args.publisher)

    got = skipped = failed = 0
    failed_list = []
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
            failed_list.append(f"{p.get('doi', '')}\t{p.get('venue', '')}\t{p.get('title', '')}")
            print(f"[{i}/{len(papers)}] not found: {stem[:50]}")
        # a pause between delay and 2 x delay seconds spreads the load more evenly
        time.sleep(args.delay * random.uniform(1.0, 2.0))

    print(f"\nDone. {got} downloaded, {skipped} already present, {failed} failed")
    if failed_list:
        Path("failed_downloads.txt").write_text("\n".join(failed_list) + "\n", "utf-8")
        print("List of failed papers written to failed_downloads.txt")
    if pw_ctx:
        pw_ctx.stop()


if __name__ == "__main__":
    main()
