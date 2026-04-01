"""
Verifii Scraper v6 — Optimized Google-first architecture
- ALL source checks use Google Search via ScraperAPI
- B2B marketplace checks (IndiaMART + TradeIndia + Justdial) combined into ONE search
- Company registration checks (MCA + Zauba Corp) combined into ONE search
- Total: 7 Google searches per verification (down from 12-18)
- This avoids ScraperAPI rate-limiting which was causing most sources to fail
"""
import asyncio
import os
import re
import httpx
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")

# Limit ScraperAPI to 4 concurrent requests to prevent Free Tier 429/timeout errors
scraper_semaphore = asyncio.Semaphore(4)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

NOISE_PHRASES = [
    "sign in", "join free", "post buy", "skip to", "search the",
    "noresults", "no results", "cookie", "privacy policy", "terms",
    "download app", "free listing", "advertise", "login", "register",
    "select language", "we are hiring", "investor relations",
    "home page", "homepage", "page not found", "error page",
    "follow us", "contact us", "about us", "sitemap",
    "all rights reserved", "copyright", "powered by",
]

GOOGLE_UI_NOISE = [
    "press / to jump to the search box",
    "ai mode all news", "ai mode all",
    "an ai overview is not available",
    "can't generate an ai overview",
    "all news videos forums images",
    "all news images forums shopping",
    "short videos more", "images short videos more",
    "videos short videos more", "shopping videos short",
    "people also ask", "related searches", "more results",
    "try again later. thinking",
    "feedback about this result", "about this result",
    "cached similar",
]

CIN_PATTERN = re.compile(r'[A-Z]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}')


def scraper_url(target_url: str, country: str = "in", render: bool = False) -> str:
    render_str = "true" if render else "false"
    return (
        f"http://api.scraperapi.com"
        f"?api_key={SCRAPER_API_KEY}"
        f"&url={target_url}"
        f"&country_code={country}"
        f"&render={render_str}"
    )


def is_noise(text: str) -> bool:
    return any(phrase in text.lower() for phrase in NOISE_PHRASES)


def is_google_noise(text: str) -> bool:
    return any(phrase in text.lower().strip() for phrase in GOOGLE_UI_NOISE)


def clean_blocks(html: str, min_len: int = 15, max_len: int = 300) -> list:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "head", "meta", "noscript"]):
        tag.decompose()
    seen = set()
    blocks = []
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "li", "td", "span", "div", "a"]):
        text = tag.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        if min_len <= len(text) <= max_len and text not in seen and not is_noise(text):
            seen.add(text)
            blocks.append(text)
    return blocks[:60]


def company_mentioned(blocks: list, query: str) -> bool:
    query_words = [w.lower() for w in query.split() if len(w) > 2]
    for block in blocks:
        block_lower = block.lower()
        if sum(1 for w in query_words if w in block_lower) >= min(2, len(query_words)):
            return True
    return False


# ── Core Google Search ────────────────────────────────────────────────────────

def _extract_google_snippets(html: str) -> tuple:
    """Extract snippets and links from Google HTML."""
    soup = BeautifulSoup(html, "html.parser")

    snippets = []
    seen = set()
    for tag in soup.find_all(["div", "span", "p"]):
        text = tag.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        if (40 < len(text) < 400
                and text not in seen
                and not is_noise(text)
                and not is_google_noise(text)):
            seen.add(text)
            snippets.append(text)

    links = []
    link_seen = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "/url?q=" in href:
            real = href.split("/url?q=")[1].split("&")[0]
            if real.startswith("http") and "google" not in real and real not in link_seen:
                link_seen.add(real)
                links.append(real)

    if not links:
        for a in soup.select("a[href^='http']"):
            href = a.get("href", "")
            if (href.startswith("http")
                    and "google" not in href
                    and "gstatic" not in href
                    and "youtube.com/results" not in href
                    and href not in link_seen):
                link_seen.add(href)
                links.append(href)

    for a in soup.select("a[data-href]"):
        href = a.get("data-href", "")
        if href.startswith("http") and "google" not in href and href not in link_seen:
            link_seen.add(href)
            links.append(href)

    return snippets[:15], links[:12]


async def _google_search_raw(query: str, num: int = 10) -> tuple:
    """Execute a Google search via ScraperAPI with 1 retry. Returns (snippets, links, full_text)."""
    target = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&hl=en&gl=in"
    url = scraper_url(target, country="in")
    timeout = 15

    for attempt in range(2):
        try:
            async with scraper_semaphore:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        snippets, links = _extract_google_snippets(resp.text)
                        return snippets, links, resp.text
        except Exception:
            if attempt == 1:
                break
            await asyncio.sleep(1)
            timeout = 20  # Increase timeout slightly on second attempt
            
    return [], [], ""


async def _google_search(query: str, source_name: str) -> dict:
    """Wrapped Google search returning a dict."""
    try:
        snippets, links, _ = await _google_search_raw(query)
        return {"source": source_name, "snippets": snippets, "links": links}
    except Exception as e:
        return {"source": source_name, "snippets": [], "links": [], "error": str(e)}


# ── Website Discovery ─────────────────────────────────────────────────────────

async def _discover_website(query: str) -> str:
    """Discover the official website of a company via Google search.
    Returns the website URL if found, or empty string."""
    try:
        search_query = f'{query} "official website" (India OR IN)'
        snippets, links, full_text = await _google_search_raw(search_query, num=8)

        query_words = [w.lower() for w in query.split() if len(w) > 2]

        # Filter out marketplace/social/directory sites
        skip_domains = [
            "indiamart.com", "tradeindia.com", "justdial.com", "linkedin.com",
            "facebook.com", "twitter.com", "instagram.com", "youtube.com",
            "wikipedia.org", "zaubacorp.com", "mca.gov.in", "google.com",
            "amazon.in", "amazon.com", "flipkart.com", "quora.com",
            "glassdoor.co.in", "glassdoor.com", "ambitionbox.com",
            "crunchbase.com", "reddit.com", "naukri.com",
            "knowyourgst.com", "gstzen.in", "cleartax.in", "mastersindia.com",
        ]

        for link in links:
            link_lower = link.lower()
            # Skip known non-company domains
            if any(d in link_lower for d in skip_domains):
                continue
            # Check if link looks like a company homepage
            domain = link.split("//")[-1].split("/")[0].replace("www.", "").lower()
            # Check if query words appear in domain or if it's a plausible company site
            domain_parts = domain.replace(".", " ").replace("-", " ").lower()
            if any(w in domain_parts for w in query_words) or len(links) <= 3:
                return link

        # Fallback: try the first non-skipped link
        for link in links:
            link_lower = link.lower()
            if not any(d in link_lower for d in skip_domains):
                return link

    except Exception:
        pass
    return ""


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def scrape_supplier(query: str, website_url: str = None, email: str = None) -> dict:
    """
    Run all checks in parallel. Combined searches reduce total API calls:
    1. Google reviews         (1 search)
    2. Google fraud           (1 search)
    3. Google complaints      (1 search)
    4. Marketplace presence   (1 search → indiamart + tradeindia + justdial)
    5. Company registration   (1 search → mca + zauba)
    6. LinkedIn presence      (1 search)
    7. Scam databases         (1 search)
    8. Website discovery+analysis (1-2 searches if no URL provided)
    """
    # Phase 1: Run core searches + website discovery in parallel
    tasks = [
        _google_reviews(query),           # 0
        _google_fraud(query),             # 1
        _google_complaints(query),        # 2
        _marketplace_presence(query),     # 3 → {"indiamart": ..., "tradeindia": ..., "justdial": ...}
        _company_registration(query),     # 4 → {"mca": ..., "zauba": ...}
        _linkedin_presence(query),        # 5
        _scam_databases(query),           # 6
    ]

    # If website URL is provided, analyze it directly; otherwise, discover it
    if website_url:
        tasks.append(_website_analysis(website_url))  # 7
    else:
        tasks.append(_discover_website(query))        # 7 → returns URL string

    if email:
        tasks.append(_email_domain_check(email))      # 8 (or 7+1)

    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    def safe(val, default):
        return default if isinstance(val, Exception) else val

    results = {}

    # Simple 1:1 mapped results
    results["google_reviews"] = safe(results_list[0], {"source": "Google Reviews", "snippets": [], "links": []})
    results["google_fraud"] = safe(results_list[1], {"source": "Google Fraud Check", "snippets": [], "links": []})
    results["google_complaints"] = safe(results_list[2], {"source": "Google Complaints", "snippets": [], "links": []})

    # Unpack combined marketplace result → 3 separate keys
    marketplace = safe(results_list[3], {})
    results["indiamart"] = marketplace.get("indiamart", {"source": "IndiaMART", "found": False})
    results["tradeindia"] = marketplace.get("tradeindia", {"source": "TradeIndia", "found": False})
    results["justdial"] = marketplace.get("justdial", {"source": "Justdial", "found": False})

    # Unpack combined registration result → 2 separate keys
    registration = safe(results_list[4], {})
    results["mca"] = registration.get("mca", {"source": "MCA Portal", "found": False})
    results["zauba"] = registration.get("zauba", {"source": "Zauba Corp", "found": False})

    results["linkedin"] = safe(results_list[5], {"source": "LinkedIn", "profile_found": False})
    results["scam_check"] = safe(results_list[6], {"source": "Scam/Blacklist Check", "risk_level": "UNKNOWN"})

    # Handle website: either direct analysis result or discovered URL needing analysis
    idx = 7
    website_result = safe(results_list[idx], None)
    if website_url:
        # Direct website analysis was run
        results["website"] = website_result or {"source": "Website Analysis", "accessible": False}
    else:
        # Website discovery was run — analyze the discovered URL
        if isinstance(website_result, str) and website_result:
            try:
                results["website"] = await _website_analysis(website_result)
            except Exception:
                results["website"] = {"source": "Website Analysis", "url": website_result, "accessible": False,
                                      "discovered": True, "error": "Could not analyze discovered website"}
        else:
            results["website"] = {"source": "Website Analysis", "accessible": False,
                                  "not_discovered": True}
    idx += 1

    if email:
        results["email_check"] = safe(results_list[idx], {"source": "Email Domain Check", "flags": []})

    return results


# ── GOOGLE REVIEWS / FRAUD / COMPLAINTS (3 searches) ────────────────────────

async def _google_reviews(query: str) -> dict:
    return await _google_search(f"{query} reviews ratings India", "Google Reviews")


async def _google_fraud(query: str) -> dict:
    data = await _google_search(f"{query} fraud scam fake India", "Google Fraud Check")
    fraud_kw = ["fraud", "scam", "fake", "cheated", "loss", "beware", "warning", "cheat", "duped"]
    consumer_noise = [
        "delivery", "refund", "return", "app", "order", "customer care",
        "expired", "damaged", "wrong product", "cancelled", "customer service",
        "helpline", "consumer forum", "poor quality", "uninstall",
    ]
    flags = []
    for s in data.get("snippets", []):
        s_lower = s.lower()
        if s_lower.startswith("press") or "jump to" in s_lower:
            continue
        if any(kw in s_lower for kw in fraud_kw):
            if any(cn in s_lower for cn in consumer_noise):
                continue
            flags.append(s)
    data["fraud_mentions"] = len(flags)
    data["fraud_snippets"] = flags[:3]
    return data


async def _google_complaints(query: str) -> dict:
    data = await _google_search(f"{query} complaint consumer forum India", "Google Complaints")
    complaint_kw = ["cheated", "not delivered", "advance payment", "money lost",
                    "fake supplier", "no response", "absconded", "fraud"]
    flags = []
    for s in data.get("snippets", []):
        s_lower = s.lower()
        if s_lower.startswith("press") or "jump to" in s_lower:
            continue
        if any(kw in s_lower for kw in complaint_kw):
            flags.append(s)
    data["complaint_count"] = len(flags)
    data["complaint_snippets"] = flags[:3]
    return data


# ── B2B MARKETPLACE PRESENCE (1 search → 3 sources) ─────────────────────────

async def _marketplace_presence(query: str) -> dict:
    """ONE Google search checks IndiaMART + TradeIndia + Justdial simultaneously.
    This is the key optimization — 1 API call instead of 3-6."""
    search_query = f'{query} (site:indiamart.com OR site:tradeindia.com OR site:justdial.com)'

    try:
        snippets, links, full_text = await _google_search_raw(search_query, num=15)
    except Exception:
        return {
            "indiamart": {"source": "IndiaMART", "found": False, "companies_found": [], "ratings": [], "years_listed": [], "verified_count": 0},
            "tradeindia": {"source": "TradeIndia", "found": False, "companies_found": [], "verified_count": 0},
            "justdial": {"source": "Justdial", "found": False, "businesses_found": [], "ratings": []},
        }

    query_words = [w.lower() for w in query.split() if len(w) > 1]

    # Classify links by source
    im_links = [l for l in links if "indiamart.com" in l]
    ti_links = [l for l in links if "tradeindia.com" in l]
    jd_links = [l for l in links if "justdial.com" in l]

    # Classify snippets by checking which source link appeared nearby
    # Since we can't easily map snippet-to-link, use keyword heuristics
    im_companies, im_ratings, im_verified = [], [], []
    ti_companies, ti_verified = [], []
    jd_businesses, jd_ratings = [], []

    for s in snippets:
        s_lower = s.lower()
        has_query = any(w in s_lower for w in query_words)

        # Determine which source this snippet belongs to
        is_indiamart = "indiamart" in s_lower or "dir.indiamart" in s_lower
        is_tradeindia = "tradeindia" in s_lower
        is_justdial = "justdial" in s_lower or "jd" in s_lower

        if is_indiamart:
            if has_query and 10 < len(s) < 250:
                im_companies.append(s)
            if any(x in s_lower for x in ["★", "/5", "rated", "stars", "rating"]):
                im_ratings.append(s)
            if any(v in s_lower for v in ["verified", "trustseal", "gst verified"]):
                im_verified.append(s)
        elif is_tradeindia:
            if has_query and 10 < len(s) < 250:
                ti_companies.append(s)
            if "verified" in s_lower:
                ti_verified.append(s)
        elif is_justdial:
            if has_query and 10 < len(s) < 250:
                jd_businesses.append(s)
            if any(x in s_lower for x in ["★", "rated", "/5", "rating", "star"]):
                jd_ratings.append(s)
        else:
            # Generic snippet — assign based on whether query matches
            if has_query and 10 < len(s) < 200:
                # Check full page text for context clues
                if any(x in s_lower for x in ["verified", "trustseal"]):
                    im_verified.append(s)

    # Also check full page text for mentions
    full_lower = full_text.lower()
    im_in_page = "indiamart" in full_lower
    ti_in_page = "tradeindia" in full_lower
    jd_in_page = "justdial" in full_lower

    return {
        "indiamart": {
            "source": "IndiaMART",
            "companies_found": im_companies[:8],
            "ratings": im_ratings[:3],
            "years_listed": [],
            "verified_count": len(im_verified),
            "found": len(im_links) > 0 or len(im_companies) > 0 or im_in_page,
        },
        "tradeindia": {
            "source": "TradeIndia",
            "companies_found": ti_companies[:5],
            "verified_count": len(ti_verified),
            "found": len(ti_links) > 0 or len(ti_companies) > 0 or ti_in_page,
        },
        "justdial": {
            "source": "Justdial",
            "businesses_found": jd_businesses[:5],
            "ratings": jd_ratings[:3],
            "found": len(jd_links) > 0 or len(jd_businesses) > 0 or jd_in_page,
        },
    }


# ── COMPANY REGISTRATION (1 search → MCA + Zauba) ───────────────────────────

async def _company_registration(query: str) -> dict:
    """ONE Google search checks MCA + Zauba Corp for company registration.
    Searches for CIN numbers, incorporation details, and company status."""
    search_query = f'{query} company CIN India (site:zaubacorp.com OR site:mca.gov.in OR "private limited" OR "limited")'

    try:
        snippets, links, full_text = await _google_search_raw(search_query, num=15)
    except Exception:
        return {
            "mca": {"source": "MCA Portal", "found": False, "companies": []},
            "zauba": {"source": "Zauba Corp", "found": False, "companies": []},
        }

    query_words = [w.lower() for w in query.split() if len(w) > 2]

    # Extract CIN numbers from full page text
    cin_matches = list(set(CIN_PATTERN.findall(full_text)))

    # Classify links
    mca_links = [l for l in links if "mca.gov.in" in l]
    zauba_links = [l for l in links if "zaubacorp.com" in l]

    full_lower = full_text.lower()
    mca_in_page = "mca.gov.in" in full_lower or "ministry of corporate" in full_lower
    zauba_in_page = "zaubacorp.com" in full_lower

    # Build companies list from CIN matches
    mca_companies = []
    zauba_companies = []
    seen_cin = set()

    for cin in cin_matches[:5]:
        if cin in seen_cin:
            continue
        seen_cin.add(cin)
        company = {
            "name": query.upper(),
            "cin": cin,
            "status": "Found via web search",
            "incorporation_date": "N/A",
            "type": "N/A",
            "state": "N/A",
        }
        mca_companies.append(company)
        zauba_companies.append({
            "name": query.upper(),
            "cin": cin,
            "status": "N/A",
            "incorporation": "N/A",
        })

    # Check snippets for company registration keywords even without CIN
    mca_keywords = ["incorporated", "incorporation", "registered company",
                    "private limited", "pvt ltd", "llp", "limited liability",
                    "ministry of corporate", "registrar of companies",
                    "active", "registered"]

    if not mca_companies:
        for s in snippets:
            s_lower = s.lower()
            if (any(w in s_lower for w in query_words) and
                    any(kw in s_lower for kw in mca_keywords)):
                cin_in_s = CIN_PATTERN.search(s)
                mca_companies.append({
                    "name": query.upper(),
                    "cin": cin_in_s.group() if cin_in_s else "N/A",
                    "status": "Registration info found in web results",
                    "incorporation_date": "N/A",
                    "type": "N/A",
                    "state": "N/A",
                })
                break

    # Zauba-specific snippets
    if not zauba_companies:
        for s in snippets:
            s_lower = s.lower()
            if "zaubacorp" in s_lower and any(w in s_lower for w in query_words):
                cin_in_s = CIN_PATTERN.search(s)
                zauba_companies.append({
                    "name": s[:80] if len(s) < 80 else query.upper(),
                    "cin": cin_in_s.group() if cin_in_s else "N/A",
                    "status": "Found on Zauba Corp",
                    "incorporation": "N/A",
                })
                break

    return {
        "mca": {
            "source": "MCA Portal",
            "companies": mca_companies[:5],
            "found": len(mca_companies) > 0 or len(mca_links) > 0 or mca_in_page,
        },
        "zauba": {
            "source": "Zauba Corp",
            "companies": zauba_companies[:5],
            "found": len(zauba_companies) > 0 or len(zauba_links) > 0 or zauba_in_page,
        },
    }


# ── LINKEDIN (1 search) ──────────────────────────────────────────────────────

async def _linkedin_presence(query: str) -> dict:
    """Check LinkedIn company presence via Google — single optimized search."""
    search_query = f'{query} site:linkedin.com/company OR site:in.linkedin.com/company'
    try:
        snippets, links, full_text = await _google_search_raw(search_query)

        linkedin_links = [l for l in links if "linkedin.com" in l]
        company_links = [l for l in linkedin_links if "/company" in l]

        # Extract relevant snippets
        query_words = [w.lower() for w in query.split() if len(w) > 1]
        relevant_snippets = []
        for s in snippets:
            s_lower = s.lower()
            if (any(w in s_lower for w in query_words) or "linkedin" in s_lower):
                if 20 < len(s) < 300 and not is_noise(s):
                    relevant_snippets.append(s)

        full_lower = full_text.lower()
        has_linkedin = "linkedin.com/company" in full_lower or len(company_links) > 0

        return {
            "source": "LinkedIn",
            "profile_found": has_linkedin or len(linkedin_links) > 0 or len(relevant_snippets) > 0,
            "links": (company_links or linkedin_links)[:3],
            "snippets": relevant_snippets[:3],
        }
    except Exception as e:
        return {"source": "LinkedIn", "profile_found": False, "error": str(e)}


# ── SCAM DATABASES (1 combined search instead of 2) ─────────────────────────

async def _scam_databases(query: str) -> dict:
    """Check for genuine B2B fraud signals — single Google search."""
    search_query = f'{query} scam fraud cheated supplier India'
    all_flags = []

    b2b_fraud_kw = [
        "fake company", "shell company", "ponzi", "absconded", "disappeared",
        "took money", "no delivery", "blacklisted", "arrested", "fir filed",
        "police case", "court order", "winding up", "struck off",
        "not genuine", "money lost", "duped", "advance payment",
    ]
    general_kw = ["scam", "fraud", "fake", "cheat", "beware", "warning"]
    consumer_noise = [
        "delivery", "refund", "return", "app", "order", "customer care",
        "expired", "damaged", "late delivery", "wrong product", "cancelled",
        "customer service", "helpline", "grievance", "consumer forum",
        "poor quality", "bad experience", "worst service", "don't buy",
        "1 star", "uninstall",
    ]

    try:
        snippets, links, _ = await _google_search_raw(search_query, num=10)

        for text in snippets:
            t = text.lower()
            if any(kw in t for kw in b2b_fraud_kw):
                all_flags.append(text)
            elif any(kw in t for kw in general_kw):
                if not any(cn in t for cn in consumer_noise):
                    all_flags.append(text)

        genuine_flags = len(all_flags)
        if genuine_flags >= 3:
            risk = "HIGH"
        elif genuine_flags >= 1:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return {
            "source": "Scam/Blacklist Check",
            "total_snippets": len(snippets),
            "fraud_flags": genuine_flags,
            "flagged_snippets": list(set(all_flags))[:4],
            "risk_level": risk,
        }
    except Exception as e:
        return {"source": "Scam/Blacklist Check", "error": str(e), "risk_level": "UNKNOWN"}


# ── WEBSITE ANALYSIS ──────────────────────────────────────────────────────────

async def _website_analysis(target_url: str) -> dict:
    if not target_url.startswith("http"):
        target_url = "https://" + target_url

    result = {
        "source": "Website Analysis",
        "url": target_url,
        "accessible": False,
        "has_contact_info": False,
        "has_address": False,
        "domain": "",
        "flags": [],
    }

    try:
        domain = target_url.split("//")[-1].split("/")[0].replace("www.", "")
        result["domain"] = domain
        free_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "rediffmail.com"]
        result["has_professional_domain"] = domain not in free_domains

        async with scraper_semaphore:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(scraper_url(target_url))
        
        result["accessible"] = resp.status_code == 200
        blocks = clean_blocks(resp.text)
        all_text = " ".join(blocks).lower()

        result["has_contact_info"] = any(kw in all_text for kw in ["contact", "phone", "email", "call us", "reach us"])
        result["has_address"] = any(kw in all_text for kw in ["address", "location", "office", "headquarter", "plot", "sector"])
        result["has_about_page"] = any(kw in all_text for kw in ["about us", "our company", "who we are"])
        result["has_product_catalog"] = any(kw in all_text for kw in ["product", "catalogue", "catalog", "price list"])

        if not result["has_contact_info"]:
            result["flags"].append("No contact information found")
        if not result["has_address"]:
            result["flags"].append("No physical address found")

        try:
            async with httpx.AsyncClient(timeout=8) as client:
                whois_resp = await client.get(f"https://api.whois.vu/?q={domain}&format=json")
                whois_data = whois_resp.json()
                creation = whois_data.get("created", "") or whois_data.get("creation_date", "")
                if creation:
                    result["domain_creation_date"] = creation
                    try:
                        created_year = int(str(creation)[:4])
                        age_years = datetime.now().year - created_year
                        result["domain_age_years"] = age_years
                        if age_years < 1:
                            result["flags"].append("Domain created very recently — high risk")
                        elif age_years < 2:
                            result["flags"].append(f"Domain only {age_years} year old — verify carefully")
                    except Exception:
                        pass
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)
        result["flags"].append("Website could not be accessed")

    return result


# ── EMAIL DOMAIN CHECK ────────────────────────────────────────────────────────

async def _email_domain_check(email: str) -> dict:
    free_providers = ["gmail.com", "yahoo.com", "yahoo.in", "hotmail.com",
                      "outlook.com", "rediffmail.com", "ymail.com"]
    result = {"source": "Email Domain Check", "email": email, "flags": []}

    if "@" not in email:
        result["flags"].append("Invalid email format")
        result["is_professional"] = False
        return result

    domain = email.split("@")[-1].lower()
    result["domain"] = domain
    result["is_professional"] = domain not in free_providers

    if not result["is_professional"]:
        result["flags"].append(f"Free email ({domain}) used — red flag for B2B")
    else:
        result["flags"].append(f"Professional email domain: {domain}")

    return result