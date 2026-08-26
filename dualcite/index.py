"""
index.py — build the precomputed index that both tabs read from.

This is the shared analytical core. It:
  1. loads the two clusters' paper lists (schema-driven, from config)
  2. parses GROBID reference XML and header XML
  3. matches citation targets back to the corpus (DOI + fuzzy title)
  4. computes citation flows and geo/affiliation aggregates
  5. caches everything to data/.precomputed/ so filter changes are instant

Nothing here is venue-specific — cluster membership, venue patterns, and field
schemas all come from the Config object.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
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
INDEX_VERSION = 9

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


def parse_refs(xml_path: Path) -> list[tuple[str, str]]:
    """Return [(title, doi)] for each citation in a processReferences XML."""
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
        if title or doi:
            refs.append((title, doi))
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
# applied to free text — a GROBID <country key="..."> attribute is authoritative
# and bypasses this check (see from_key below).
AMBIGUOUS_CC = {
    "AI",  # Anguilla vs "Artificial Intelligence"
    "ML",  # Mali vs "Machine Learning"
    "IS",  # Iceland vs the word "is" / "Information Systems"
    "AS",  # American Samoa vs "as"
    "OR",  # Oregon-ish / "or"  (not a country anyway)
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
    "MO",  # Macao — keep? "MO" = Missouri. Macao resolves via alias.
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


def _extract_country(text: str) -> str | None:
    if not text:
        return None
    code = normalize_country(text)
    if code:
        return code
    words = text.split()
    for w in reversed(words):
        w = w.strip(" .,;()")
        if len(w) >= 2:
            code = normalize_country(w)
            if code:
                return code
    for i in range(len(words) - 1):
        code = normalize_country(f"{words[i]} {words[i+1]}".strip(" .,;()"))
        if code:
            return code
    # GROBID sometimes puts a city or region in the <country> tag
    # (e.g. "Pisa"). Fall back to a small city map.
    low = text.lower().strip(" .,;()")
    if low in CITY_COUNTRY:
        return CITY_COUNTRY[low]
    return None


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
    "singapore": "SG", "london": "GB", "cambridge": "GB", "oxford": "GB",
    "edinburgh": "GB", "manchester": "GB", "dublin": "IE",
    "boston": "US", "cambridge, ma": "US", "new york": "US",
    "pittsburgh": "US", "seattle": "US", "chicago": "US",
    "toronto": "CA", "montreal": "CA", "montréal": "CA",
    "sydney": "AU", "melbourne": "AU", "delhi": "IN", "bangalore": "IN",
    "mumbai": "IN", "hyderabad": "IN", "tel aviv": "IL", "haifa": "IL",
    "moscow": "RU", "warsaw": "PL", "prague": "CZ", "athens": "GR",
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
    ("university of montreal", "CA"), ("mila", "CA"),
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
    # More US — state universities, UC system, common abbreviations
    ("michigan state", "US"), ("northeastern university", "US"),
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
    ("fraunhofer", "DE"), ("dfki", "DE"), ("kit ", "DE"),
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
    # Russia and CIS (explicit — avoid generic 'state university' misfires)
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
    ("northeastern university, china", "CN"), ("ocean university", "CN"),
    ("beijing institute of technology", "CN"), ("jinan university", "CN"),
    ("cas ", "CN"), ("institute of computing technology", "CN"),
    ("institute of automation", "CN"), ("institute of software", "CN"),
    # More Japan
    ("electro-communications", "JP"), ("kyushu", "JP"), ("titech", "JP"),
    ("okinawa", "JP"), ("nict", "JP"),
]


def _country_from_institution(name: str) -> str | None:
    """Guess a country from a bare institution name (no address/country tag)."""
    if not name:
        return None
    # pad so patterns ending in a space (e.g. "ucl ", "mit ") also match when
    # the token sits at the very end of the string
    low = " " + name.lower() + " "
    for kw, code in INSTITUTION_HINTS:
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
    # word — i.e. the name already looks complete and the city is tacked on
    # ("Tsinghua University | Beijing"). This protects names that legitimately
    # END in a place ("National University of | Singapore").
    if last in CITY_COUNTRY and prev in INST_TAIL:
        cut = " ".join(tokens[:-1]).strip()
        if len(cut.split()) >= 2:
            return cut
    return name


def parse_header(xml_path: Path) -> tuple[list[str], list[str]]:
    """Return (countries, institutions) from a processHeaderDocument XML."""
    if not xml_path.exists():
        return [], []
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return [], []
    countries, institutions = set(), set()
    for aff in tree.iter(f"{TEI}affiliation"):
        aff_insts = []      # institution names (for the institutions list)
        aff_all_org = []    # ALL org text incl. department/laboratory (for inference)
        for org in aff.findall(f"{TEI}orgName"):
            txt = (org.text or "").strip()
            if not txt:
                continue
            otype = (org.get("type") or "").lower()
            if otype == "institution":
                clean = _clean_institution(txt)
                institutions.add(clean)
                aff_insts.append(clean)
            aff_all_org.append(txt)

        aff_country_found = False
        for addr in aff.findall(f"{TEI}address"):
            cel = addr.find(f"{TEI}country")
            if cel is not None:
                code = normalize_country(cel.get("key", ""), from_key=True) or \
                       _extract_country((cel.text or "").strip())
                if code:
                    countries.add(code)
                    aff_country_found = True
            # settlement / region often hold a city that implies a country
            # (and GROBID sometimes misplaces the city here while putting
            # junk like "University" in <country>).
            if not aff_country_found:
                for tag in ("settlement", "region", "addrLine"):
                    el = addr.find(f"{TEI}{tag}")
                    if el is not None:
                        code = _extract_country((el.text or "").strip())
                        if code:
                            countries.add(code)
                            aff_country_found = True
                            break
        for cel in aff.findall(f"{TEI}country"):
            code = normalize_country(cel.get("key", ""), from_key=True) or \
                   _extract_country((cel.text or "").strip())
            if code:
                countries.add(code)
                aff_country_found = True

        # fallback: infer from any org name (institution, dept, or lab)
        if not aff_country_found:
            for name in aff_insts + aff_all_org:
                code = _country_from_institution(name)
                if code:
                    countries.add(code)
                    break
    return sorted(countries), sorted(institutions)


# ============================== data loading ==============================

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
            if title.lower().startswith("proceedings of the"):
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
                "id": pid, "title": title, "doi": doi, "venue": venue,
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
    if not norm:
        return (norm, None)
    if norm in _W_SET:
        return (norm, norm)
    if len(norm.split()) < _W_MINWORDS:
        return (norm, None)
    r = process.extractOne(norm, _W_LIST, scorer=fuzz.ratio,
                           score_cutoff=_W_THRESHOLD)
    return (norm, r[0] if r else None)


# ============================== index building ==============================

def _cache_path(cfg: Config) -> Path:
    return cfg.path("precomputed") / "index.json"


def build_index(cfg: Config, force: bool = False, quiet: bool = False) -> dict:
    """Build (or load) the full precomputed index."""
    cache = _cache_path(cfg)
    if cache.exists() and not force:
        try:
            c = json.loads(cache.read_text("utf-8"))
            if c.get("version") == INDEX_VERSION:
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
        for t, _ in refs:
            n = norm_title(t)
            if n:
                unique.add(n)
    unique_list = list(unique)
    log(f"Matching {len(unique_list)} unique cited titles...")

    norm_to_corpus = {}
    nw = min(cpu_count(), 8)
    with Pool(nw, _init_worker,
              (title_set, title_list, cfg.fuzzy_threshold,
               cfg.min_words_for_fuzzy)) as pool:
        chunk = max(1, len(unique_list) // (nw * 8))
        for cited_norm, matched in pool.map(_match_one, unique_list, chunk):
            if matched is not None:
                norm_to_corpus[cited_norm] = norm_to_pid[matched]
    log(f"  matched {len(norm_to_corpus)}")

    # --- resolve citations ---
    citations = {}
    total_refs = {}   # per paper: total unique references made (incl. outside corpus)
    for pid, refs in all_refs.items():
        cited = set()
        unique = set()
        for t, d in refs:
            # count unique references (dedup by DOI or normalized title)
            key = d if d else (norm_title(t) or f"_anon_{len(unique)}")
            unique.add(key)
            tgt = None
            if d and d in doi_to_id:
                tgt = doi_to_id[d]
            else:
                n = norm_title(t)
                if n:
                    tgt = norm_to_corpus.get(n)
            if tgt and tgt != pid:
                cited.add(tgt)
        citations[pid] = sorted(cited)
        total_refs[pid] = len(unique)

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
    affiliations = {}
    n_with_country = 0
    for pid, p in papers.items():
        # header filename uses the same stem as refs, in the cluster subfolder
        h_path = headers_root / p["cluster"] / f"{pid}.xml"
        countries, institutions = parse_header(h_path)
        affiliations[pid] = {"countries": countries, "institutions": institutions}
        if countries:
            n_with_country += 1
    log(f"  {n_with_country}/{len(papers)} papers with country data")

    index = {
        "version": INDEX_VERSION,
        "papers": papers,
        "citations": citations,
        "total_refs": total_refs,
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
