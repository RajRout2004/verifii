"""
Verifii Scraper v3 — Robust multi-source supplier research
Fixes: MCA correct URL, LinkedIn via ScraperAPI, Zauba correct URL,
       cleaner B2B marketplace text extraction, Google via ScraperAPI
"""
import asyncio
import os
import re
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Navigation/UI noise to filter out
NOISE_PHRASES = [
    "sign in", "join free", "post buy", "skip to", "search the",
    "noresults", "no results", "cookie", "privacy policy", "terms",
    "download app", "free listing", "advertise", "login", "register",
    "select language", "we are hiring", "investor relations",
    "home page", "homepage", "page not found", "error page",
    "follow us", "contact us", "about us", "sitemap",
    "all rights reserved", "copyright", "powered by",
]


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
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in NOISE_PHRASES)


def clean_blocks(html: str, min_len: int = 15, max_len: int = 300) -> list:
    """Extract clean, meaningful text blocks — filter out navigation noise."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "head", "meta", "noscript"]):
        tag.decompose()
    seen = set()
    blocks = []
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "li", "td", "span", "div", "a"]):
        text = tag.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        if (min_len <= len(text) <= max_len
                and text not in seen
                and not is_noise(text)):
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


async def scrape_supplier(query: str, website_url: str = None, email: str = None) -> dict:
    tasks = [
        _google_reviews(query),
        _google_fraud(query),
        _google_complaints(query),
        _indiamart(query),
        _tradeindia(query),
        _justdial(query),
        _mca_portal(query),
        _zauba_corp(query),
        _linkedin_presence(query),
        _scam_databases(query),
    ]
    if website_url:
        tasks.append(_website_analysis(website_url))
    if email:
        tasks.append(_email_domain_check(email))

    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    keys = [
        "google_reviews", "google_fraud", "google_complaints",
        "indiamart", "tradeindia", "justdial",
        "mca", "zauba", "linkedin", "scam_check"
    ]
    if website_url:
        keys.append("website")
    if email:
        keys.append("email_check")

    results = {}
    for key, val in zip(keys, results_list):
        results[key] = {"error": str(val), "source": key} if isinstance(val, Exception) else val
    return results


# ── GOOGLE (via ScraperAPI to avoid bot detection) ────────────────────────────

async def _google_reviews(query: str) -> dict:
    return await _google_search(f"{query} supplier India reviews site:indiamart.com OR site:tradeindia.com OR site:justdial.com", "Google Reviews")


async def _google_fraud(query: str) -> dict:
    data = await _google_search(f"{query} fraud scam fake complaints India", "Google Fraud Check")
    fraud_kw = ["fraud", "scam", "fake", "cheated", "complaint", "loss", "beware", "warning", "cheat", "duped"]
    snippets = data.get("snippets", [])
    flags = [s for s in snippets if any(kw in s.lower() for kw in fraud_kw)]
    data["fraud_mentions"] = len(flags)
    data["fraud_snippets"] = flags[:3]
    return data


async def _google_complaints(query: str) -> dict:
    data = await _google_search(f"{query} complaint consumer forum India", "Google Complaints")
    complaint_kw = ["complaint", "issue", "problem", "refund", "cheated", "not delivered", "poor quality"]
    snippets = data.get("snippets", [])
    flags = [s for s in snippets if any(kw in s.lower() for kw in complaint_kw)]
    data["complaint_count"] = len(flags)
    data["complaint_snippets"] = flags[:3]
    return data


async def _google_search(query: str, source_name: str) -> dict:
    target = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10&hl=en&gl=in"
    url = scraper_url(target, country="in")
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            snippets = []
            for tag in soup.find_all(["div", "span", "p"]):
                text = tag.get_text(separator=" ", strip=True)
                text = re.sub(r'\s+', ' ', text)
                if 40 < len(text) < 400 and not is_noise(text) and text not in snippets:
                    snippets.append(text)
            links = []
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if "/url?q=" in href:
                    real = href.split("/url?q=")[1].split("&")[0]
                    if real.startswith("http") and "google" not in real:
                        links.append(real)
            return {"source": source_name, "snippets": snippets[:8], "links": links[:5]}
    except Exception as e:
        return {"source": source_name, "snippets": [], "error": str(e)}


# ── INDIAMART ─────────────────────────────────────────────────────────────────

async def _indiamart(query: str) -> dict:
    target = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target))
            blocks = clean_blocks(resp.text)
            found = company_mentioned(blocks, query)

            ratings = [b for b in blocks if any(x in b for x in ["★", "/5", "Rated", "stars"]) and len(b) < 80]
            years = [b for b in blocks if re.search(r'(since|est\.?|established)\s*\d{4}', b.lower())]
            verified = [b for b in blocks if "verified" in b.lower() and len(b) < 60]
            # Clean company names — must have query words, reasonable length
            companies = [
                b for b in blocks
                if any(w.lower() in b.lower() for w in query.split() if len(w) > 2)
                and len(b) < 100 and len(b) > 8
            ][:5]

            return {
                "source": "IndiaMART",
                "companies_found": companies,
                "ratings": ratings[:3],
                "years_listed": years[:2],
                "verified_count": len(verified),
                "found": found or len(companies) > 0,
            }
    except Exception as e:
        return {"source": "IndiaMART", "error": str(e), "found": False}


# ── TRADEINDIA ────────────────────────────────────────────────────────────────

async def _tradeindia(query: str) -> dict:
    target = f"https://www.tradeindia.com/search/?q={query.replace(' ', '+')}&cat=company"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target))
            blocks = clean_blocks(resp.text)
            found = company_mentioned(blocks, query)
            verified = [b for b in blocks if "verified" in b.lower() and len(b) < 60]
            companies = [
                b for b in blocks
                if any(w.lower() in b.lower() for w in query.split() if len(w) > 2)
                and len(b) < 100
            ][:5]

            return {
                "source": "TradeIndia",
                "companies_found": companies,
                "verified_count": len(verified),
                "found": found or len(companies) > 0,
            }
    except Exception as e:
        return {"source": "TradeIndia", "error": str(e), "found": False}


# ── JUSTDIAL ──────────────────────────────────────────────────────────────────

async def _justdial(query: str) -> dict:
    target = f"https://www.justdial.com/All-India/{query.replace(' ', '-')}/nct-10215168"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target))
            blocks = clean_blocks(resp.text)
            found = company_mentioned(blocks, query)
            ratings = [b for b in blocks if any(x in b for x in ["★", "Rated", "/5", "Rating"]) and len(b) < 80]
            businesses = [
                b for b in blocks
                if any(w.lower() in b.lower() for w in query.split() if len(w) > 2)
                and len(b) < 100
            ][:5]

            return {
                "source": "Justdial",
                "businesses_found": businesses,
                "ratings": ratings[:3],
                "found": found or len(businesses) > 0,
            }
    except Exception as e:
        return {"source": "Justdial", "error": str(e), "found": False}


# ── MCA PORTAL (correct URL) ──────────────────────────────────────────────────

async def _mca_portal(query: str) -> dict:
    # Use the correct MCA company name search page
    target = f"https://www.mca.gov.in/mcafoportal/showCheckCompanyName.do"
    search_target = f"https://efiling.mca.gov.in/efs-filing/rest/getCompanyINC/getCompanyDetails?companyName={query.replace(' ', '%20')}&companyType=&roc="

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # Try the JSON API first
            resp = await client.get(scraper_url(search_target))
            try:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    companies = []
                    for c in data[:5]:
                        name = c.get("companyName") or c.get("company_name", "")
                        if name and any(w.lower() in name.lower() for w in query.split() if len(w) > 2):
                            companies.append({
                                "name": name,
                                "cin": c.get("cin", "N/A"),
                                "status": c.get("companyStatus", c.get("status", "N/A")),
                                "incorporation_date": c.get("dateOfIncorporation", "N/A"),
                                "type": c.get("companyType", "N/A"),
                                "state": c.get("registeredState", "N/A"),
                            })
                    if companies:
                        return {"source": "MCA Portal", "companies": companies, "found": True}
            except Exception:
                pass

            # Fallback: scrape the MCA check company name page
            mca_scrape = f"https://www.mca.gov.in/mcafoportal/showCheckCompanyName.do?companyName={query.replace(' ', '+')}"
            resp2 = await client.get(scraper_url(mca_scrape))
            blocks = clean_blocks(resp2.text)
            found = company_mentioned(blocks, query)

            cin_pattern = re.compile(r'[A-Z]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}')
            companies = []
            for block in blocks:
                cin_match = cin_pattern.search(block)
                if cin_match and any(w.lower() in block.lower() for w in query.split() if len(w) > 2):
                    companies.append({
                        "name": query,
                        "cin": cin_match.group(),
                        "status": "Found on MCA",
                        "incorporation_date": "N/A",
                        "type": "N/A",
                        "state": "N/A",
                    })

            # Also check Zauba which mirrors MCA data
            zauba_target = f"https://www.zaubacorp.com/company-list/p-1/company-name-{query.replace(' ', '-').upper()}.html"
            resp3 = await client.get(scraper_url(zauba_target))
            blocks3 = clean_blocks(resp3.text)
            cin_found = []
            for block in blocks3:
                cin_match = cin_pattern.search(block)
                if cin_match:
                    name_part = block.replace(cin_match.group(), "").strip()
                    cin_found.append({
                        "name": name_part[:80] or query,
                        "cin": cin_match.group(),
                        "status": "N/A",
                        "incorporation_date": "N/A",
                        "type": "N/A",
                        "state": "N/A",
                    })

            all_companies = companies + cin_found
            return {
                "source": "MCA Portal",
                "companies": all_companies[:5],
                "found": found or len(all_companies) > 0,
            }
    except Exception as e:
        return {"source": "MCA Portal", "error": str(e), "found": False}


# ── ZAUBA CORP (fixed URL) ────────────────────────────────────────────────────

async def _zauba_corp(query: str) -> dict:
    # Correct Zauba search URL
    target = f"https://www.zaubacorp.com/company-list/p-1/company-name-{query.replace(' ', '-').upper()}.html"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target))
            blocks = clean_blocks(resp.text)
            found = company_mentioned(blocks, query)

            cin_pattern = re.compile(r'[A-Z]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}')
            companies = []
            for block in blocks:
                cin_match = cin_pattern.search(block)
                if cin_match:
                    name_part = re.sub(cin_pattern, '', block).strip()
                    if any(w.lower() in name_part.lower() for w in query.split() if len(w) > 2):
                        companies.append({
                            "name": name_part[:80] or query,
                            "cin": cin_match.group(),
                            "status": "N/A",
                            "incorporation": "N/A",
                        })

            return {
                "source": "Zauba Corp",
                "companies": companies[:5],
                "found": found or len(companies) > 0,
            }
    except Exception as e:
        return {"source": "Zauba Corp", "error": str(e), "found": False}


# ── LINKEDIN (via ScraperAPI Google search) ───────────────────────────────────

async def _linkedin_presence(query: str) -> dict:
    target = f"https://www.google.com/search?q=%22{query.replace(' ', '+')}%22+site:linkedin.com/company&gl=in"
    url = scraper_url(target, country="in")
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            linkedin_links = []
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if "/url?q=" in href:
                    real = href.split("/url?q=")[1].split("&")[0]
                    if "linkedin.com/company" in real:
                        linkedin_links.append(real)

            snippets = []
            for tag in soup.find_all(["div", "span"]):
                text = tag.get_text(separator=" ", strip=True)
                if "linkedin" in text.lower() and 20 < len(text) < 300 and not is_noise(text):
                    snippets.append(text)

            return {
                "source": "LinkedIn",
                "profile_found": len(linkedin_links) > 0,
                "links": linkedin_links[:3],
                "snippets": snippets[:3],
            }
    except Exception as e:
        return {"source": "LinkedIn", "profile_found": False, "error": str(e)}


# ── SCAM DATABASES ────────────────────────────────────────────────────────────

async def _scam_databases(query: str) -> dict:
    queries = [
        f"{query} scam India",
        f"{query} fraud complaint India",
        f"{query} cheated supplier review",
    ]
    all_snippets = []
    all_flags = []
    fraud_kw = ["scam", "fraud", "fake", "cheat", "complaint", "beware",
                "warning", "not genuine", "money lost", "not delivered", "duped"]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for q in queries:
                target = f"https://www.google.com/search?q={q.replace(' ', '+')}&num=5&gl=in"
                resp = await client.get(scraper_url(target, country="in"))
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup.find_all(["div", "span", "p"]):
                    text = tag.get_text(separator=" ", strip=True)
                    if 30 < len(text) < 400 and not is_noise(text):
                        all_snippets.append(text)
                        if any(kw in text.lower() for kw in fraud_kw):
                            all_flags.append(text)

        return {
            "source": "Scam/Blacklist Check",
            "total_snippets": len(all_snippets),
            "fraud_flags": len(all_flags),
            "flagged_snippets": list(set(all_flags))[:4],
            "risk_level": "HIGH" if len(all_flags) >= 3 else "MEDIUM" if len(all_flags) >= 1 else "LOW",
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

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
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

        # WHOIS domain age
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