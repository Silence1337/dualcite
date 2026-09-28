"""
index.py: build the precomputed index that both tabs read from.

This is the shared analytical core. It:
  1. loads the two clusters' paper lists (schema-driven, from config)
  2. parses GROBID reference XML and header XML
  3. matches citation targets back to the corpus (DOI + fuzzy title)
  4. computes citation flows and geo/affiliation aggregates
  5. caches everything to data/.precomputed/ so filter changes are instant

Nothing here is venue-specific, cluster membership, venue patterns, and field
schemas all come from the Config object.
"""
from __future__ import annotations

import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from multiprocessing import Pool, cpu_count
from pathlib import Path

from .config import Config

try:
    from rapidfuzz import fuzz, process
except ImportError:
    sys.exit("rapidfuzz required:  pip install rapidfuzz")

try:
    import pycountry
except ImportError:
    pycountry = None   # geo features degrade gracefully

TEI = "{http://www.tei-c.org/ns/1.0}"
INDEX_VERSION = 13

# ============================== title normalization ==============================

STOP_WORDS = {
    "a", "an", "the", "and", "of", "to", "for", "in", "on", "at", "by", "with",
    "without", "from", "into", "through", "during", "including", "excluding",
    "such", "as", "or", "but", "not", "this", "that", "these", "those", "they",
    "we", "you", "he", "she", "it", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "having", "do", "does", "did", "doing",
    "will", "would", "could", "should",
}


def norm_title(t: str) -> str:
    if not t:
        return ""
    t = re.sub(r"^\d{4}[a-z]?\s*\.\s*", "", t, flags=re.I).lower()
    t = re.sub(r"[^\w\s]", "", t)
    return " ".join(w for w in t.split() if w not in STOP_WORDS)


# ============================== filename helpers ==============================

def sanitize_title(t: str, n: int = 80) -> str:
    s = re.sub(r"[^\w\s-]", "", t)[:n].strip()
    return re.sub(r"\s+", "_", s)


def doi_suffix(d: str) -> str:
    return d.rsplit("/", 1)[-1] if d else "unknown"


# ============================== venue resolution ==============================

def resolve_venue(source: str, cfg: Config) -> str | None:
    s = (source or "").lower()
    for venue, patterns in cfg.venue_patterns.items():
        for p in patterns:
            if p in s:
                return venue
    return None


# ============================== XML parsing ==============================

def _full_text(elem) -> str:
    return "".join(elem.itertext()).strip() if elem is not None else ""


def parse_refs(xml_path: Path) -> list[tuple[str, str, int | None]]:
    """Return [(title, doi, year)] for each citation in a processReferences XML."""
    if not xml_path.exists():
        return []
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []
    refs = []
    for bib in tree.iter(f"{TEI}biblStruct"):
        title = ""
        analytic = bib.find(f"{TEI}analytic")
        if analytic is not None:
            t = analytic.find(f"{TEI}title")
            if t is not None:
                title = _full_text(t)
        if not title:
            monogr = bib.find(f"{TEI}monogr")
            if monogr is not None:
                for t in monogr.findall(f"{TEI}title"):
                    if (t.get("level") or "") in ("m", ""):
                        title = _full_text(t)
                        if title:
                            break
        doi = ""
        for idno in bib.iter(f"{TEI}idno"):
            if (idno.get("type") or "").upper() == "DOI":
                d = (_full_text(idno) or "").lower()
                if d:
                    doi = d
                    break
        year = None
        for date in bib.iter(f"{TEI}date"):
            m = re.match(r"(\d{4})", date.get("when") or "")
            if m:
                year = int(m.group(1))
                break
        if title or doi:
            refs.append((title, doi, year))
    return refs


# ---- affiliation / country parsing (from header XML) ----

COUNTRY_ALIASES = {
    "usa": "US", "u.s.a.": "US", "u.s.": "US", "united states": "US",
    "united states of america": "US", "us": "US", "uk": "GB", "u.k.": "GB",
    "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "people's republic of china": "CN", "p.r. china": "CN", "pr china": "CN",
    "china": "CN", "mainland china": "CN", "republic of korea": "KR",
    "south korea": "KR", "korea": "KR", "taiwan": "TW", "hong kong": "HK",
    "macao": "MO", "macau": "MO", "russia": "RU", "russian federation": "RU",
    "czech republic": "CZ", "czechia": "CZ", "the netherlands": "NL",
    "netherlands": "NL", "holland": "NL", "iran": "IR", "vietnam": "VN",
    "viet nam": "VN", "uae": "AE", "united arab emirates": "AE",
    "saudi arabia": "SA", "singapore": "SG", "japan": "JP", "india": "IN",
    "germany": "DE", "france": "FR", "italy": "IT", "italia": "IT",
    "spain": "ES", "españa": "ES", "brazil": "BR", "brasil": "BR",
    "canada": "CA", "australia": "AU", "israel": "IL", "switzerland": "CH",
    "sweden": "SE", "norway": "NO", "finland": "FI", "denmark": "DK",
    "austria": "AT", "belgium": "BE", "portugal": "PT", "greece": "GR",
    "poland": "PL", "ireland": "IE", "new zealand": "NZ", "turkey": "TR",
    "türkiye": "TR", "egypt": "EG", "mexico": "MX", "colombia": "CO",
    "chile": "CL", "argentina": "AR", "malaysia": "MY", "indonesia": "ID",
    "thailand": "TH", "philippines": "PH", "pakistan": "PK", "bangladesh": "BD",
    "south africa": "ZA", "romania": "RO", "hungary": "HU", "ukraine": "UA",
    "中国": "CN", "日本": "JP", "한국": "KR", "대한민국": "KR",
}


# Two-letter ISO codes that are far more often non-country abbreviations in
# free-text academic affiliations than the actual (tiny) country. Bare
# occurrences of these in free text are NOT treated as countries. This is only
# applied to free text, a GROBID <country key="..."> attribute is authoritative
# and bypasses this check (see from_key below).
AMBIGUOUS_CC = {
    "AI",  # Anguilla vs "Artificial Intelligence"
    "ML",  # Mali vs "Machine Learning"
    "IS",  # Iceland vs the word "is" / "Information Systems"
    "AS",  # American Samoa vs "as"
    "OR",  # the word "or"; also Oregon
    "SO",  # Somalia vs "so"
    "TO",  # Tonga vs "to"
    "AM",  # Armenia vs "am"
    "ME",  # Montenegro vs "me"
    "AL",  # Albania vs "AL" (Alabama, et al.)
    "LA",  # Laos vs "LA" (Los Angeles, Louisiana)
    "AD",  # Andorra vs "ad"
    "BA",  # Bosnia vs "BA" (degree)
    "MS",  # Montserrat vs "MS" (degree, Microsoft)
    "MD",  # Moldova vs "MD" (Maryland, doctor)
    "MT",  # Malta vs "MT" (Montana, mount)
    "MO",  # Macao vs "MO" (Missouri); Macao is still matched by its name
}


def normalize_country(raw: str, from_key: bool = False) -> str | None:
    if not raw or pycountry is None:
        return None
    raw = raw.strip()
    if len(raw) == 2 and raw.isalpha():
        code = raw.upper()
        # skip ambiguous codes when they come from free text (not a key attr)
        if not from_key and code in AMBIGUOUS_CC:
            return None
        if pycountry.countries.get(alpha_2=code):
            return code
    lower = raw.lower().strip(" .,;")
    if lower in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[lower]
    if len(raw) >= 5 and not raw.isupper():
        try:
            r = pycountry.countries.search_fuzzy(raw)
            if r:
                return r[0].alpha_2
        except LookupError:
            pass
    return None


US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"}
# Words that are country names but usually mean a US state or a city here.
_AMBIGUOUS_WORDS = {"georgia", "jersey", "victoria", "washington", "guinea"}


def _country_exact(s: str) -> str | None:
    """Exact country lookup (aliases, ISO codes, official names); no fuzzy search."""
    s = s.strip(" .,;()")
    if not s or pycountry is None:
        return None
    low = s.lower()
    if low in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[low]
    if len(s) == 2 and s.isalpha():
        code = s.upper()
        if code in AMBIGUOUS_CC:
            return None
        return code if pycountry.countries.get(alpha_2=code) else None
    try:
        return pycountry.countries.lookup(s).alpha_2
    except LookupError:
        return None


def _extract_countries(text: str) -> list[str]:
    """
    All countries named in a free-text string. GROBID sometimes merges the
    countries of several affiliations ("India Italy") or appends an author name
    ("United Kingdom Richard ..."), so the string is scanned for two-word and
    one-word country names instead of being read as a single name. Fuzzy
    matching is used only as a last resort on short strings.
    """
    if not text:
        return []
    whole = _country_exact(text)
    if whole:
        return [whole]
    words = [w.strip(" .,;()") for w in text.split()]
    found, used = [], set()
    for i in range(len(words) - 1):
        code = _country_exact(f"{words[i]} {words[i+1]}")
        if code:
            found.append(code); used |= {i, i + 1}
    for i, w in enumerate(words):
        if i in used or len(w) < 2 or w.lower() in _AMBIGUOUS_WORDS:
            continue
        code = _country_exact(w)
        if code:
            found.append(code)
    if not found:
        low = text.lower().strip(" .,;()")
        if low in CITY_COUNTRY:
            found.append(CITY_COUNTRY[low])
        elif 5 <= len(text) and len(words) <= 3:
            code = normalize_country(text)
            if code:
                found.append(code)
    found = list(dict.fromkeys(found))
    # "Hong Kong SAR, China", "Taiwan, Province of China": keep the region only
    if "CN" in found and any(c in found for c in ("HK", "MO", "TW")):
        found.remove("CN")
    return found


# Cities that GROBID occasionally mislabels as countries. Kept small and
# unambiguous (major research hubs only).
CITY_COUNTRY = {
    "pisa": "IT", "rome": "IT", "milan": "IT", "turin": "IT", "bologna": "IT",
    "paris": "FR", "lyon": "FR", "grenoble": "FR", "toulouse": "FR",
    "berlin": "DE", "munich": "DE", "münchen": "DE", "hamburg": "DE",
    "heidelberg": "DE", "stuttgart": "DE", "darmstadt": "DE",
    "madrid": "ES", "barcelona": "ES", "valencia": "ES",
    "amsterdam": "NL", "rotterdam": "NL", "utrecht": "NL",
    "vienna": "AT", "wien": "AT", "zurich": "CH", "zürich": "CH",
    "geneva": "CH", "beijing": "CN", "shanghai": "CN", "shenzhen": "CN",
    "hangzhou": "CN", "guangzhou": "CN", "nanjing": "CN", "wuhan": "CN",
    "tokyo": "JP", "kyoto": "JP", "osaka": "JP", "seoul": "KR",
    "singapore": "SG", "london": "GB", "oxford": "GB",
    "edinburgh": "GB", "manchester": "GB", "dublin": "IE",
    "boston": "US", "new york": "US",
    "pittsburgh": "US", "seattle": "US", "chicago": "US",
    "toronto": "CA", "montreal": "CA", "montréal": "CA",
    "sydney": "AU", "melbourne": "AU", "delhi": "IN", "bangalore": "IN",
    "mumbai": "IN", "hyderabad": "IN", "tel aviv": "IL", "haifa": "IL",
    "moscow": "RU", "shenyang": "CN", "warsaw": "PL", "prague": "CZ", "athens": "GR",
    "stockholm": "SE", "copenhagen": "DK", "oslo": "NO", "helsinki": "FI",
}


# Keyword -> ISO alpha-2. Checked as lower-cased substrings against an
# institution name when no explicit country tag is present. Ordered from more
# specific to less; first hit wins. This recovers country for the very common
# GROBID case where only <orgName type="institution"> is extracted (e.g.
# "Tsinghua University" with no <country> tag).
INSTITUTION_HINTS = [
    # China
    ("tsinghua", "CN"), ("peking university", "CN"), ("fudan", "CN"),
    ("zhejiang", "CN"), ("shanghai", "CN"), ("beijing", "CN"),
    ("chinese academy", "CN"), ("harbin", "CN"), ("nanjing", "CN"),
    ("wuhan", "CN"), ("sun yat", "CN"), ("renmin university", "CN"),
    ("university of science and technology of china", "CN"),
    ("huazhong", "CN"), ("xiamen", "CN"), ("tianjin", "CN"),
    ("shenzhen", "CN"), ("guangzhou", "CN"), ("sichuan university", "CN"),
    ("beihang", "CN"), ("tongji", "CN"), ("southeast university", "CN"),
    ("alibaba", "CN"), ("tencent", "CN"), ("baidu", "CN"), ("huawei", "CN"),
    # Hong Kong / Macao / Taiwan
    ("hong kong", "HK"), ("hkust", "HK"), ("polyu", "HK"),
    ("national taiwan", "TW"), ("tsing hua university", "TW"),
    ("academia sinica", "TW"), ("macau", "MO"), ("macao", "MO"),
    # South Korea
    ("seoul national", "KR"), ("kaist", "KR"), ("korea university", "KR"),
    ("yonsei", "KR"), ("postech", "KR"), ("sungkyunkwan", "KR"),
    ("chung-ang", "KR"), ("hanyang", "KR"), ("naver", "KR"),
    ("korea advanced institute", "KR"), ("gwangju institute", "KR"),
    # Japan
    ("university of tokyo", "JP"), ("kyoto university", "JP"),
    ("osaka university", "JP"), ("tohoku", "JP"), ("nagoya", "JP"),
    ("tokyo institute of technology", "JP"), ("waseda", "JP"),
    ("keio", "JP"), ("riken", "JP"), ("nara institute", "JP"),
    ("hokkaido", "JP"), ("kyushu university", "JP"), ("tsukuba", "JP"),
    # Singapore
    ("national university of singapore", "SG"), ("nanyang", "SG"),
    ("singapore management university", "SG"),
    ("singapore university of technology", "SG"), ("a*star", "SG"),
    # India
    ("indian institute of technology", "IN"), ("iit ", "IN"),
    ("indian institute of science", "IN"), ("iiit", "IN"),
    ("indian statistical institute", "IN"), ("jadavpur", "IN"),
    ("amrita", "IN"), ("anna university", "IN"), ("bits pilani", "IN"),
    # USA
    ("stanford", "US"), ("massachusetts institute of technology", "US"),
    ("mit ", "US"), ("carnegie mellon", "US"), ("harvard", "US"),
    ("university of chicago", "US"), ("berkeley", "US"),
    ("university of california", "US"), ("university of washington", "US"),
    ("cornell", "US"), ("princeton", "US"), ("yale", "US"),
    ("columbia university", "US"), ("new york university", "US"),
    ("university of pennsylvania", "US"), ("university of michigan", "US"),
    ("university of texas", "US"), ("georgia institute", "US"),
    ("georgia tech", "US"), ("university of illinois", "US"),
    ("johns hopkins", "US"), ("ucla", "US"), ("usc ", "US"),
    ("university of maryland", "US"), ("university of massachusetts", "US"),
    ("penn state", "US"), ("ohio state", "US"), ("purdue", "US"),
    ("university of southern california", "US"), ("caltech", "US"),
    ("northwestern university", "US"), ("duke university", "US"),
    ("university of wisconsin", "US"), ("university of minnesota", "US"),
    ("university of pittsburgh", "US"), ("nvidia", "US"), ("google", "US"),
    ("microsoft", "US"), ("meta ai", "US"), ("amazon", "US"),
    ("ibm ", "US"), ("apple", "US"), ("adobe", "US"), ("salesforce", "US"),
    ("allen institute", "US"), ("cohere", "US"),
    # UK
    ("university of cambridge", "GB"), ("university of oxford", "GB"),
    ("imperial college", "GB"), ("university college london", "GB"),
    ("ucl ", "GB"), ("university of edinburgh", "GB"),
    ("university of manchester", "GB"), ("king's college london", "GB"),
    ("university of sheffield", "GB"), ("queen mary", "GB"),
    ("university of glasgow", "GB"), ("university of birmingham", "GB"),
    ("deepmind", "GB"),
    # Germany
    ("technical university of munich", "DE"), ("tu munich", "DE"),
    ("lmu munich", "DE"), ("heidelberg", "DE"), ("rwth aachen", "DE"),
    ("max planck", "DE"), ("darmstadt", "DE"), ("saarland", "DE"),
    ("university of stuttgart", "DE"), ("karlsruhe", "DE"),
    ("humboldt", "DE"), ("university of hamburg", "DE"),
    ("bosch", "DE"), ("sap ", "DE"),
    # France
    ("sorbonne", "FR"), ("inria", "FR"), ("cnrs", "FR"),
    ("université", "FR"), ("universite", "FR"), ("paris", "FR"),
    ("grenoble", "FR"), ("école", "FR"), ("ecole", "FR"),
    # Canada
    ("university of toronto", "CA"), ("mcgill", "CA"),
    ("university of waterloo", "CA"), ("université de montréal", "CA"),
    ("university of montreal", "CA"), (" mila ", "CA"),
    ("university of british columbia", "CA"), ("university of alberta", "CA"),
    ("vector institute", "CA"),
    # Others
    ("technion", "IL"), ("tel aviv", "IL"), ("hebrew university", "IL"),
    ("bar-ilan", "IL"), ("ben-gurion", "IL"), ("weizmann", "IL"),
    ("eth zurich", "CH"), ("epfl", "CH"), ("university of zurich", "CH"),
    ("kth royal institute", "SE"), ("chalmers", "SE"),
    ("university of amsterdam", "NL"), ("delft", "NL"),
    ("university of edinburgh", "GB"), ("aalto", "FI"),
    ("university of melbourne", "AU"), ("university of sydney", "AU"),
    ("monash", "AU"), ("australian national university", "AU"),
    ("university of queensland", "AU"), ("unsw", "AU"),
    ("pontificia", "BR"), ("universidade de são paulo", "BR"),
    ("universidade de sao paulo", "BR"),
    ("king abdullah university", "SA"), ("kaust", "SA"),
    ("universität wien", "AT"), ("university of vienna", "AT"),
    # Netherlands
    ("leiden", "NL"), ("university of amsterdam", "NL"), ("delft", "NL"),
    ("utrecht", "NL"), ("radboud", "NL"), ("eindhoven", "NL"),
    ("groningen", "NL"), ("tilburg", "NL"), ("vrije universiteit", "NL"),
    ("twente", "NL"), ("maastricht", "NL"),
    # Denmark / Nordics
    ("aarhus", "DK"), ("copenhagen", "DK"), ("technical university of denmark", "DK"),
    ("aalborg", "DK"), ("university of oslo", "NO"), ("ntnu", "NO"),
    ("bergen", "NO"), ("uppsala", "SE"), ("lund university", "SE"),
    ("gothenburg", "SE"), ("stockholm university", "SE"),
    ("linköping", "SE"), ("university of helsinki", "FI"), ("aalto", "FI"),
    ("university of turku", "FI"), ("university of iceland", "IS"),
    # Italy
    ("university of bologna", "IT"), ("sapienza", "IT"), ("politecnico di", "IT"),
    ("university of pisa", "IT"), ("cnr-ilc", "IT"), ("fondazione bruno kessler", "IT"),
    ("fbk", "IT"), ("university of padua", "IT"), ("padova", "IT"),
    ("university of trento", "IT"), ("università di", "IT"), ("universita di", "IT"),
    ("turin", "IT"), ("torino", "IT"), ("milano", "IT"), ("napoli", "IT"),
    # Poland / Central & Eastern Europe
    ("university of warsaw", "PL"), ("warsaw university", "PL"),
    ("jagiellonian", "PL"), ("wrocław", "PL"), ("wroclaw", "PL"),
    ("poznań", "PL"), ("poznan", "PL"), ("adam mickiewicz", "PL"),
    ("kempelen institute", "SK"), ("slovak", "SK"),
    ("charles university", "CZ"), ("czech technical", "CZ"),
    ("brno", "CZ"), ("masaryk", "CZ"), ("university of ljubljana", "SI"),
    ("budapest", "HU"), ("eötvös", "HU"), ("university of zagreb", "HR"),
    ("university of bucharest", "RO"), ("babeș-bolyai", "RO"),
    # Spain / Portugal
    ("universitat politècnica", "ES"), ("universitat pompeu fabra", "ES"),
    ("barcelona", "ES"), ("universidad", "ES"), ("universidad de madrid", "ES"),
    ("autónoma de madrid", "ES"), ("universidade de lisboa", "PT"),
    ("universidade do porto", "PT"), ("instituto superior técnico", "PT"),
    ("lisbon", "PT"),
    # Belgium / Switzerland / Austria
    ("ku leuven", "BE"), ("ghent university", "BE"), ("université libre de bruxelles", "BE"),
    ("uclouvain", "BE"), ("university of geneva", "CH"), ("university of basel", "CH"),
    ("idiap", "CH"), ("graz", "AT"), ("johannes kepler", "AT"),
    # Ireland / Greece / Turkey / Middle East
    ("trinity college dublin", "IE"), ("university college dublin", "IE"),
    ("dublin city university", "IE"), ("national university of ireland", "IE"),
    ("aristotle university", "GR"), ("athens", "GR"),
    ("national technical university of athens", "GR"),
    ("bogazici", "TR"), ("boğaziçi", "TR"), ("middle east technical", "TR"),
    ("bilkent", "TR"), ("koç university", "TR"), ("sabanci", "TR"),
    ("king saud", "SA"), ("qatar computing", "QA"), ("qatar university", "QA"),
    ("khalifa university", "AE"), ("mbzuai", "AE"),
    # Latin America / Africa
    ("unicamp", "BR"), ("universidade federal", "BR"),
    ("universidad de chile", "CL"), ("universidad de buenos aires", "AR"),
    ("universidad nacional", "AR"), ("cape town", "ZA"),
    ("university of pretoria", "ZA"), ("witwatersrand", "ZA"),
    ("cairo university", "EG"), ("nile university", "EG"),
    # More China
    ("south china university", "CN"), ("east china", "CN"),
    ("central china", "CN"), ("northwestern polytechnical", "CN"),
    ("dalian", "CN"), ("jilin university", "CN"), ("shandong university", "CN"),
    ("chongqing", "CN"), ("xi'an jiaotong", "CN"), ("jiaotong", "CN"),
    ("hunan university", "CN"), ("central south university", "CN"),
    ("university of electronic science and technology", "CN"),
    ("microsoft research asia", "CN"), ("bytedance", "CN"),
    ("ant group", "CN"), ("meituan", "CN"), ("xiaomi", "CN"),
    # More India
    ("indian institute of information technology", "IN"),
    ("delhi", "IN"), ("mumbai", "IN"), ("bangalore", "IN"),
    ("hyderabad", "IN"), ("chennai", "IN"), ("kanpur", "IN"),
    ("kharagpur", "IN"), ("madras", "IN"), ("guwahati", "IN"),
    # More US, state universities, UC system, common abbreviations
    ("michigan state", "US"), ("northeastern university, china", "CN"), ("northeastern university, shenyang", "CN"),
    ("northeastern university", "US"),
    ("arizona state", "US"), ("texas a&m", "US"), ("texas a & m", "US"),
    ("uc davis", "US"), ("uc san diego", "US"), ("uc irvine", "US"),
    ("uc santa barbara", "US"), ("uc riverside", "US"), ("uc merced", "US"),
    ("uc berkeley", "US"), ("ucsd", "US"), ("ucsb", "US"),
    ("rutgers", "US"), ("boston university", "US"),
    ("virginia tech", "US"), ("north carolina", "US"), ("nc state", "US"),
    ("indiana university", "US"), ("university of colorado", "US"),
    ("university of florida", "US"), ("university of arizona", "US"),
    ("university of utah", "US"), ("university of rochester", "US"),
    ("university of notre dame", "US"), ("notre dame", "US"),
    ("brown university", "US"), ("dartmouth", "US"),
    ("university of virginia", "US"), ("stony brook", "US"),
    ("university of iowa", "US"), ("university of oregon", "US"),
    ("emory university", "US"), ("vanderbilt", "US"), ("rice university", "US"),
    ("washington university", "US"), ("university of california", "US"),
    ("lehigh", "US"), ("drexel", "US"), ("rensselaer", "US"),
    ("university of houston", "US"), ("university of georgia", "US"),
    ("temple university", "US"), ("george mason", "US"),
    ("university of buffalo", "US"), ("university at buffalo", "US"),
    ("colorado state", "US"), ("oregon state", "US"), ("iowa state", "US"),
    ("kansas state", "US"), ("florida state", "US"), ("san diego state", "US"),
    ("intel corp", "US"), ("intel labs", "US"), ("bloomberg", "US"), ("linkedin", "US"),
    ("openai", "US"), ("anthropic", "US"), ("apple inc", "US"),
    ("j.p. morgan", "US"), ("jpmorgan", "US"), ("capital one", "US"),
    ("mit-ibm", "US"), ("los alamos", "US"), ("oak ridge", "US"),
    ("argonne", "US"), ("sandia", "US"), ("mitre", "US"),
    # Germany with diacritics / more
    ("würzburg", "DE"), ("wurzburg", "DE"), ("tübingen", "DE"),
    ("tubingen", "DE"), ("universität", "DE"), ("universitaet", "DE"),
    ("bielefeld", "DE"), ("bonn", "DE"), ("cologne", "DE"), ("köln", "DE"),
    ("freiburg", "DE"), ("mannheim", "DE"), ("potsdam", "DE"),
    ("leipzig", "DE"), ("dresden", "DE"), ("bochum", "DE"),
    ("fraunhofer", "DE"), ("dfki", "DE"), (" kit ", "DE"),
    # Poland
    ("nask", "PL"), ("wut", "PL"), ("agh university", "PL"),
    ("gdańsk", "PL"), ("gdansk", "PL"), ("łódź", "PL"), ("lodz", "PL"),
    # More UK
    ("university of warwick", "GB"), ("university of leeds", "GB"),
    ("university of bristol", "GB"), ("university of southampton", "GB"),
    ("university of nottingham", "GB"), ("cardiff university", "GB"),
    ("lancaster university", "GB"), ("university of surrey", "GB"),
    ("university of york", "GB"), ("newcastle university", "GB"),
    ("university of liverpool", "GB"), ("university of essex", "GB"),
    ("heriot-watt", "GB"), ("university of bath", "GB"),
    # Canada more
    ("university of ottawa", "CA"), ("york university", "CA"),
    ("simon fraser", "CA"), ("dalhousie", "CA"), ("queen's university", "CA"),
    ("concordia university", "CA"), ("university of calgary", "CA"),
    # Japan / Korea more
    ("tokyo metropolitan", "JP"), ("nagoya institute", "JP"),
    ("japan advanced institute", "JP"), ("ntt ", "JP"),
    ("sony", "JP"), ("fujitsu", "JP"), ("nec ", "JP"), ("rakuten", "JP"),
    ("ewha", "KR"), ("kt corporation", "KR"), ("lg ai", "KR"),
    ("samsung", "KR"), ("upstage", "KR"),
    # Others with common patterns
    ("hong kong university of science", "HK"),
    ("city university of hong kong", "HK"),
    ("chinese university of hong kong", "HK"),
    ("indian institute", "IN"), ("iisc", "IN"),
    # Russia and CIS (explicit, avoid generic 'state university' misfires)
    ("moscow", "RU"), ("lomonosov", "RU"), ("saint petersburg", "RU"),
    ("st. petersburg", "RU"), ("st petersburg", "RU"), ("skoltech", "RU"),
    ("higher school of economics", "RU"), ("hse university", "RU"),
    ("novosibirsk", "RU"), ("tomsk", "RU"), ("yandex", "RU"),
    ("innopolis", "RU"), ("mipt", "RU"), ("itmo", "RU"),
    ("kazan", "RU"), ("ural federal", "RU"),
    ("nazarbayev", "KZ"), ("kyiv", "UA"), ("kharkiv", "UA"),
    ("belarusian state", "BY"), ("minsk", "BY"),
    # Additional institutions and labs seen in the corpus
    ("sap se", "DE"), ("sap ", "DE"), ("heidelberg institute", "DE"),
    ("alibaba", "CN"), ("peking", "CN"), ("moe key lab", "CN"),
    ("x-lance", "CN"), ("state key laboratory", "CN"),
    ("university of notre", "US"), ("notre dame", "US"),
    ("ineeji", "KR"), ("lg corp", "KR"), ("kakao", "KR"),
    # Iran
    ("sharif university", "IR"), ("tehran", "IR"), ("amirkabir", "IR"),
    ("iran university", "IR"), ("isfahan", "IR"),
    # More US
    ("pennsylvania state", "US"), ("penn state", "US"),
    ("university of connecticut", "US"), ("university of delaware", "US"),
    # More China (universities + labs)
    ("noah's ark", "CN"), ("noah ark", "CN"),
    ("guangdong university", "CN"), ("nankai", "CN"), ("soochow", "CN"),
    ("shandong", "CN"), ("hefei", "CN"), ("university of macau", "MO"),
    ("ocean university", "CN"),
    ("beijing institute of technology", "CN"), ("jinan university", "CN"),
    ("cas ", "CN"), ("institute of computing technology", "CN"),
    ("institute of automation", "CN"), ("institute of software", "CN"),
    # More Japan
    ("electro-communications", "JP"), ("kyushu", "JP"), ("titech", "JP"),
    ("okinawa", "JP"), ("nict", "JP"),
]


# Longer keywords are more specific ("microsoft research asia" before
# "microsoft", "universidad de chile" before "universidad"), so they are tried
# first. Duplicates are removed.
_HINTS_BY_LENGTH = sorted(dict(INSTITUTION_HINTS).items(), key=lambda kv: -len(kv[0]))


def _country_from_institution(name: str) -> str | None:
    """Guess a country from a bare institution name (no address/country tag)."""
    if not name:
        return None
    # pad so patterns ending in a space (e.g. "ucl ", "mit ") also match when
    # the token sits at the very end of the string
    low = " " + name.lower() + " "
    for kw, code in _HINTS_BY_LENGTH:
        if kw in low:
            return code
    return None


def _clean_institution(name: str) -> str:
    """
    Strip a trailing city that GROBID appended to an institution name, so
    "Tsinghua University Beijing" and "Tsinghua University" don't count as two
    separate institutions.

    Conservative: only strips trailing tokens that are clearly appended
    location, never touches the core name. Handles:
      "University of Amsterdam Amsterdam"  -> "University of Amsterdam"
      "Tsinghua University Beijing"        -> "Tsinghua University"
      "City University of Hong Kong Hong Kong" -> "City University of Hong Kong"
    """
    if not name:
        return name
    tokens = name.split()
    if len(tokens) < 3:
        return name

    # Known multi-word cities to strip from the end (longest first).
    MULTI_CITY = ["hong kong", "new york", "san diego", "san francisco",
                  "los angeles", "cape town", "abu dhabi", "tel aviv"]
    low = name.lower()
    for city in MULTI_CITY:
        suffix = " " + city
        if low.endswith(suffix):
            # strip it, unless the name IS just the city
            cut = name[: len(name) - len(suffix)].strip()
            if len(cut.split()) >= 2:
                return cut

    # Single trailing token: strip if it's a known city OR repeats the previous
    # token (GROBID's "Amsterdam Amsterdam" duplication).
    INST_TAIL = {"university", "institute", "college", "school", "academy",
                 "laboratory", "lab", "technology", "sciences", "science",
                 "group", "corporation", "corp", "center", "centre", "china",
                 "singapore"}  # words a real name legitimately ends on
    last = tokens[-1].lower().strip(",.")
    prev = tokens[-2].lower().strip(",.")

    # exact duplication is always safe to strip ("... Amsterdam Amsterdam")
    if last == prev:
        cut = " ".join(tokens[:-1]).strip()
        if len(cut.split()) >= 2:
            return cut

    # strip a trailing city ONLY if the token before it is an institutional
    # word, i.e. the name already looks complete and the city is tacked on
    # ("Tsinghua University | Beijing"). This protects names that legitimately
    # END in a place ("National University of | Singapore").
    if last in CITY_COUNTRY and prev in INST_TAIL:
        cut = " ".join(tokens[:-1]).strip()
        if len(cut.split()) >= 2:
            return cut
    return name


# ACM papers print the conference short name, year, and location on their
# first page ("SIGIR '25, Padua, Italy"). GROBID sometimes parses this line as
# an author affiliation, which would assign every such paper to the host
# country. The tag below recognizes the conference marker ("SIGIR '25",
# "CHIIR '25", "WWW'25", ...).
FOOTER_TAG = re.compile(r"\b[A-Z][A-Za-z]{1,11}\s*['\u2019\u2018`]\s?\d{2}\b")
_ADDR_FIELDS = ("settlement", "region", "addrLine", "country")


def _norm_tag(t: str) -> str:
    return re.sub(r"[\s'\u2019\u2018`]", "", t).upper()


def _aff_tag(aff) -> str | None:
    """Return the normalized conference tag if this affiliation contains one."""
    m = FOOTER_TAG.search(" ".join(aff.itertext()))
    return _norm_tag(m.group(0)) if m else None


def _org_texts_without_tag(aff) -> list[tuple[str, str]]:
    out = []
    for org in aff.findall(f"{TEI}orgName"):
        txt = FOOTER_TAG.sub(" ", org.text or "")
        txt = re.sub(r"\s+", " ", txt).strip(" ,;")
        if txt:
            out.append(((org.get("type") or "").lower(), txt))
    return out


def learn_footer_locations(xml_paths, min_share: float = 0.6,
                           min_count: int = 3) -> dict[str, dict]:
    """
    Learn the printed location of each conference from the affiliations that
    carry its footer tag. The conference location occurs in (almost) every
    such affiliation, while genuine author addresses that GROBID merged into
    some of them vary, so only address words occurring in at least
    `min_share` of the tagged affiliations are kept. Returns
    {tag: {"tokens": {lower-case words}, "codes": {country codes}}}.
    """
    seen: dict[str, int] = {}
    counts: dict[str, dict[str, int]] = {}
    for path in xml_paths:
        try:
            raw = Path(path).read_text("utf-8", errors="ignore")
        except OSError:
            continue
        # the apostrophe may be stored as an XML entity, so this raw check is
        # only a cheap prefilter; the real check runs on the parsed text
        if not re.search(r"(?:'|&apos;|&#39;|&#x27;|\u2019|&#8217;)\s?\d{2}", raw):
            continue
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            continue
        for aff in root.iter(f"{TEI}affiliation"):
            tag = _aff_tag(aff)
            if not tag:
                continue
            words = set()
            for addr in aff.findall(f"{TEI}address"):
                for fld in _ADDR_FIELDS:
                    el = addr.find(f"{TEI}{fld}")
                    if el is not None:
                        words |= {w.lower().strip(" .,;()") for w in (el.text or "").split()}
            words.discard("")
            seen[tag] = seen.get(tag, 0) + 1
            c = counts.setdefault(tag, {})
            for w in words:
                c[w] = c.get(w, 0) + 1
    locs: dict[str, dict] = {}
    for tag, n in seen.items():
        if n < min_count:
            continue
        tokens = {w for w, k in counts[tag].items() if k >= min_share * n}
        codes = {code for code in (normalize_country(w) for w in tokens) if code}
        if tokens:
            locs[tag] = {"tokens": tokens, "codes": codes}
    return locs


def _strip_tokens(text: str, tokens: set) -> str:
    if not tokens:
        return text
    return " ".join(w for w in text.split()
                    if w.lower().strip(" .,;()") not in tokens)


_SOURCE_RANK = {"key": 0, "text": 1, "address": 2, "inferred": 3}


def parse_header(xml_path: Path, footer_locs: dict | None = None) -> dict:
    """
    Return {"countries", "institutions", "inst_country", "country_source"} for
    a processHeaderDocument XML. inst_country pairs each institution with the
    countries of its own affiliation; country_source records how each country
    was found: key (GROBID code), text (country element), address (city,
    region, or address line), or inferred (from an organization name).
    """
    empty = {"countries": [], "institutions": [], "inst_country": [], "country_source": {}}
    if not xml_path.exists():
        return empty
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return empty
    footer_locs = footer_locs or {}
    source: dict[str, str] = {}
    institutions, inst_country = set(), set()

    def add(code, how, bucket):
        bucket.add(code)
        if code not in source or _SOURCE_RANK[how] < _SOURCE_RANK[source[code]]:
            source[code] = how

    for aff in tree.iter(f"{TEI}affiliation"):
        tag = _aff_tag(aff)
        orgs = _org_texts_without_tag(aff) if tag else [
            ((o.get("type") or "").lower(), (o.text or "").strip())
            for o in aff.findall(f"{TEI}orgName") if (o.text or "").strip()]
        if tag and not orgs:
            continue    # pure conference footer, not an affiliation
        strip = footer_locs.get(tag, {}) if tag else {}
        strip_tokens, strip_codes = strip.get("tokens", set()), strip.get("codes", set())
        aff_insts = [_clean_institution(t) for k, t in orgs if k == "institution"]
        aff_all_org = [t for _, t in orgs]
        here: set[str] = set()

        country_els = [a.find(f"{TEI}country") for a in aff.findall(f"{TEI}address")]
        country_els += aff.findall(f"{TEI}country")
        for cel in [c for c in country_els if c is not None]:
            key = (cel.get("key") or "").upper()
            code = normalize_country(key, from_key=True) if key and key not in strip_codes else None
            if code:
                add(code, "key", here)
                continue
            for c in _extract_countries(_strip_tokens((cel.text or "").strip(), strip_tokens)):
                add(c, "text", here)
        if not here:
            for addr in aff.findall(f"{TEI}address"):
                for fld in ("region", "settlement", "addrLine"):
                    el = addr.find(f"{TEI}{fld}")
                    if el is None:
                        continue
                    txt = _strip_tokens((el.text or "").strip(), strip_tokens)
                    if txt.replace(".", "").upper() in US_STATES:
                        add("US", "address", here)     # "CA", "VA": US states, not countries
                        break
                    codes = _extract_countries(txt)
                    for c in codes:
                        add(c, "address", here)
                    if codes:
                        break
        if not here:
            for name in aff_insts + aff_all_org:
                code = _country_from_institution(name)
                if code:
                    add(code, "inferred", here)
                    break
        for inst in aff_insts:
            institutions.add(inst)
            inst_country.add((inst, tuple(sorted(here))))
    countries = sorted(source)
    return {"countries": countries, "institutions": sorted(institutions),
            "inst_country": [[i, list(c)] for i, c in sorted(inst_country)],
            "country_source": source}


# ============================== data loading ==============================

def _clean_markup(title: str) -> str:
    """
    Remove markup that some metadata sources (Crossref) keep in titles, such as
    <scp>Fin-Fact</scp> or <i>ImageScope</i>, so that the title can be matched
    against references. The paper id, which names its XML files, is built from
    the original title and is not affected.
    """
    t = re.sub(r"<[^>]+>", "", title or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def load_papers(cfg: Config) -> tuple[dict, dict, dict]:
    """
    Returns (papers, doi_to_id, ref_xml_paths).
    papers[pid] = {id, title, doi, venue, cluster, year, url}
    """
    papers, doi_to_id, ref_paths = {}, {}, {}
    refs_root = cfg.path("refs_xml")

    for cluster_key in ("a", "b"):
        sch = cfg.schema[cluster_key]
        refs_dir = refs_root / cluster_key   # per-cluster subfolder
        papers_path = cfg.path("papers_a" if cluster_key == "a" else "papers_b")
        if not papers_path.exists():
            print(f"  Warning: {papers_path} not found, skipping cluster "
                  f"{cluster_key}", file=sys.stderr)
            continue
        raw = json.loads(papers_path.read_text("utf-8"))

        for p in raw:
            title = p.get(sch["title"]) or ""
            pid_raw = str(p.get(sch["id"]) or "") if sch.get("id") else ""
            if (title.lower().startswith(tuple(cfg.exclude_title_prefixes))
                    or (pid_raw and pid_raw.endswith(tuple(cfg.exclude_id_suffixes)))
                    or (pid_raw and cfg.include_id_prefixes
                        and not pid_raw.startswith(tuple(cfg.include_id_prefixes)))):
                continue

            # resolve venue by trying, in order:
            #   1. the direct venue field (short name like "CIKM")
            #   2. the free-text source field via patterns
            #   3. any patterns matched anywhere in the direct field
            # A paper's venue may live in either field depending on its source
            # (e.g. DBLP puts "CIKM" in `venue`; other sources put a long
            # proceedings title in `source`). We accept whichever resolves to a
            # known venue for this cluster.
            cluster_venues = cfg.clusters[cluster_key].venues
            venue = None

            direct = (p.get(sch["venue"]) or "").lower() if sch.get("venue") else ""
            if direct in cluster_venues:
                venue = direct

            if venue is None and sch.get("venue_from"):
                v = resolve_venue(p.get(sch["venue_from"], ""), cfg)
                if v in cluster_venues:
                    venue = v

            # last resort: try pattern-matching the direct field too
            if venue is None and direct:
                v = resolve_venue(direct, cfg)
                if v in cluster_venues:
                    venue = v

            if venue is None:
                continue
            src_text = " ".join(str(p.get(sch.get(k) or "", "") or "")
                                for k in ("venue", "venue_from")).lower()
            if any(x in src_text for x in cfg.exclude_patterns):
                continue

            doi = (p.get(sch["doi"]) or "").strip().lower() if sch.get("doi") else ""

            # paper id: explicit field, or reconstruct filename stem
            if sch.get("id"):
                pid = p.get(sch["id"])
                if not pid:
                    continue
                ref_paths[pid] = refs_dir / f"{pid}.xml"
            else:
                # id is the XML filename stem: sanitize(title)__doi_suffix
                stem = f"{sanitize_title(title)}__{doi_suffix(doi)}"
                pid = stem
                ref_paths[pid] = refs_dir / f"{stem}.xml"

            url = p.get("url") or (f"https://doi.org/{doi}" if doi else "")
            papers[pid] = {
                "id": pid, "title": _clean_markup(title), "doi": doi, "venue": venue,
                "cluster": cluster_key, "year": p.get("year"), "url": url,
            }
            if doi:
                doi_to_id[doi] = pid

    return papers, doi_to_id, ref_paths


# ============================== fuzzy matching (multiprocessing) ==============================

_W_SET: set = set()
_W_LIST: list = []
_W_THRESHOLD = 85
_W_MINWORDS = 4


def _init_worker(title_set, title_list, threshold, minwords):
    global _W_SET, _W_LIST, _W_THRESHOLD, _W_MINWORDS
    _W_SET, _W_LIST = title_set, title_list
    _W_THRESHOLD, _W_MINWORDS = threshold, minwords


def _match_one(norm):
    """Return (cited_norm, matched_corpus_norm, score, kind)."""
    if not norm:
        return (norm, None, 0.0, None)
    if norm in _W_SET:
        return (norm, norm, 100.0, "exact")
    if len(norm.split()) < _W_MINWORDS:
        return (norm, None, 0.0, None)
    # _W_THRESHOLD holds the candidate floor here; candidates between the floor
    # and the acceptance threshold are kept only for the sensitivity analysis.
    r = process.extractOne(norm, _W_LIST, scorer=fuzz.ratio,
                           score_cutoff=_W_THRESHOLD)
    return (norm, r[0], round(float(r[1]), 1), "fuzzy") if r else (norm, None, 0.0, None)


# ============================== index building ==============================

def _cache_path(cfg: Config) -> Path:
    return cfg.path("precomputed") / "index.json"


def _fingerprint(cfg: Config) -> str:
    """Hash of everything the index depends on besides the code: the analysis
    settings of the configuration, the content of the paper lists, and the number
    and total size of the XML files. File dates are not used, so a cached index
    stays valid after the repository is cloned. A change makes the index rebuild."""
    import hashlib
    parts = {
        "clusters": {k: sorted(c.venues) for k, c in cfg.clusters.items()},
        "patterns": cfg.venue_patterns, "schema": cfg.schema,
        "matching": [cfg.fuzzy_threshold, cfg.fuzzy_floor, cfg.min_words_for_fuzzy, cfg.max_year_gap],
        "exclude": [cfg.exclude_patterns, cfg.exclude_title_prefixes, cfg.exclude_id_suffixes,
                    cfg.include_id_prefixes],
    }
    for key in ("papers_a", "papers_b"):          # small files: hash their content
        try:
            parts[key] = hashlib.sha1(cfg.path(key).read_bytes()).hexdigest()
        except (OSError, KeyError):
            parts[key] = None
    # XML folders: the files sit in subfolders a/ and b/; count and measure them
    for key in ("refs_xml", "headers_xml"):
        n = size = 0
        try:
            for f in cfg.path(key).rglob("*.xml"):
                n += 1; size += f.stat().st_size
        except (OSError, KeyError):
            pass
        parts[key] = [n, size]
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def build_index(cfg: Config, force: bool = False, quiet: bool = False) -> dict:
    """Build (or load) the full precomputed index."""
    cache = _cache_path(cfg)
    if cache.exists() and not force:
        try:
            c = json.loads(cache.read_text("utf-8"))
            if c.get("version") == INDEX_VERSION and c.get("fingerprint") == _fingerprint(cfg):
                if not quiet:
                    print(f"  Index loaded from {cache}", file=sys.stderr)
                return c
        except Exception:
            pass

    log = (lambda m: None) if quiet else (lambda m: print(m, file=sys.stderr))

    log("Loading papers...")
    papers, doi_to_id, ref_paths = load_papers(cfg)
    log(f"  {len(papers)} papers")
    for ck in ("a", "b"):
        n = sum(1 for p in papers.values() if p["cluster"] == ck)
        found = sum(1 for pid, p in papers.items()
                    if p["cluster"] == ck and ref_paths[pid].exists())
        log(f"  cluster {ck} ({cfg.clusters[ck].short}): {n} papers, "
            f"{found} ref-XML found")

    # --- parse all reference XML ---
    log("Parsing reference XML...")
    all_refs = {}
    for i, pid in enumerate(papers):
        if not quiet and i % 500 == 0:
            print(f"  {i}/{len(papers)}\r", file=sys.stderr, end="")
        all_refs[pid] = parse_refs(ref_paths[pid])
    log(f"  parsed {len(papers)} papers      ")

    # --- build normalized-title index of the corpus ---
    norm_to_pid = {}
    for pid, p in papers.items():
        n = norm_title(p["title"])
        if n and n not in norm_to_pid:
            norm_to_pid[n] = pid
    title_list = list(norm_to_pid)
    title_set = set(title_list)

    # --- collect unique cited titles, fuzzy-match in parallel ---
    unique = set()
    for refs in all_refs.values():
        for t, _, _ in refs:
            n = norm_title(t)
            if n:
                unique.add(n)
    unique_list = list(unique)
    log(f"Matching {len(unique_list)} unique cited titles...")

    floor = min(cfg.fuzzy_threshold, cfg.fuzzy_floor)
    norm_to_match = {}          # cited_norm -> (pid, score, kind)
    nw = min(cpu_count(), 8)
    with Pool(nw, _init_worker,
              (title_set, title_list, floor, cfg.min_words_for_fuzzy)) as pool:
        chunk = max(1, len(unique_list) // (nw * 8))
        for cited_norm, matched, score, kind in pool.map(_match_one, unique_list, chunk):
            if matched is not None:
                norm_to_match[cited_norm] = (norm_to_pid[matched], score, kind)
    log(f"  candidates: {len(norm_to_match)}")

    def _year(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    # --- resolve citations ---
    # Every candidate link is logged with its kind (doi / exact / fuzzy), score,
    # the year of the cited reference, and whether that year is compatible with
    # the target paper. A reference published years before the target paper
    # cannot cite it (e.g. LoRA, 2021, matched by title to DenseLoRA, 2025).
    # The accepted citations use the configured threshold and the year check;
    # the full log supports the robustness and sensitivity analyses.
    citations, total_refs, match_log = {}, {}, []
    for pid, refs in all_refs.items():
        cited, unique = set(), set()
        for t, d, y in refs:
            unique.add(d if d else (norm_title(t) or f"_anon_{len(unique)}"))
            tgt = kind = None
            score = 0.0
            if d and d in doi_to_id:
                tgt, score, kind = doi_to_id[d], 100.0, "doi"
            else:
                n = norm_title(t)
                if n and n in norm_to_match:
                    tgt, score, kind = norm_to_match[n]
            if not tgt or tgt == pid:
                continue
            ty = _year(papers[tgt].get("year"))
            year_ok = kind == "doi" or y is None or ty is None or y >= ty - cfg.max_year_gap
            match_log.append([pid, tgt, kind, score, y, year_ok, t])
            if year_ok and (kind != "fuzzy" or score >= cfg.fuzzy_threshold):
                cited.add(tgt)
        citations[pid] = sorted(cited)
        total_refs[pid] = len(unique)
    n_year = sum(1 for m in match_log if not m[5])
    log("  accepted links by kind: " + ", ".join(
        f"{k}={sum(1 for m in match_log if m[2] == k and m[5] and (k != 'fuzzy' or m[3] >= cfg.fuzzy_threshold))}"
        for k in ("doi", "exact", "fuzzy")) + f"; rejected by year check: {n_year}")

    n_edges = sum(len(v) for v in citations.values())
    log(f"  {n_edges} intra-corpus citations")

    # --- flow breakdown ---
    flows = {"a_a": 0, "a_b": 0, "b_a": 0, "b_b": 0}
    for src, tgts in citations.items():
        sc = papers[src]["cluster"]
        for t in tgts:
            tc = papers[t]["cluster"]
            flows[f"{sc}_{tc}"] += 1
    log(f"  flows: {flows}")

    # --- affiliations (header XML) ---
    log("Parsing affiliations...")
    headers_root = cfg.path("headers_xml")
    footer_locs = learn_footer_locations(
        headers_root / p["cluster"] / f"{pid}.xml" for pid, p in papers.items())
    if footer_locs:
        log("  conference footers detected: " + ", ".join(
            f"{t} ({', '.join(sorted(v['codes'])) or '?'})" for t, v in sorted(footer_locs.items())))
    affiliations = {}
    n_with_country = 0
    for pid, p in papers.items():
        # header filename uses the same stem as refs, in the cluster subfolder
        h_path = headers_root / p["cluster"] / f"{pid}.xml"
        affiliations[pid] = parse_header(h_path, footer_locs)
        countries = affiliations[pid]["countries"]
        if countries:
            n_with_country += 1
    log(f"  {n_with_country}/{len(papers)} papers with country data")

    index = {
        "version": INDEX_VERSION,
        "fingerprint": _fingerprint(cfg),
        "papers": papers,
        "citations": citations,
        "total_refs": total_refs,
        "match_log": match_log,
        "affiliations": affiliations,
        "flows": flows,
    }

    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache.write_text(json.dumps(index, ensure_ascii=False), "utf-8")
        log(f"  Index saved to {cache}")
    except Exception as e:
        log(f"  Cache save failed: {e}")

    return index


# ============================== derived stats (per-paper) ==============================

def compute_citation_stats(index: dict) -> dict:
    """
    Per-paper in/out citation counts split by internal/external cluster.
    Returns {pid: {ii, ie, oi, oe}}.
    """
    papers = index["papers"]
    citations = index["citations"]
    ii = defaultdict(int); ie = defaultdict(int)
    oi = defaultdict(int); oe = defaultdict(int)
    for src, tgts in citations.items():
        if src not in papers:
            continue
        sc = papers[src]["cluster"]
        for t in tgts:
            if t not in papers:
                continue
            if papers[t]["cluster"] == sc:
                oi[src] += 1; ii[t] += 1
            else:
                oe[src] += 1; ie[t] += 1
    return {pid: {"ii": ii.get(pid, 0), "ie": ie.get(pid, 0),
                  "oi": oi.get(pid, 0), "oe": oe.get(pid, 0)}
            for pid in papers}
