"""
Verifii Scraper — Robust multi-source supplier research
Uses text-based extraction instead of fragile CSS selectors.
ScraperAPI routes Indian sites through Indian IPs.
Google works directly from Render.
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


def scraper_url(target_url: str, country: str = "in") -> str:
    return (
        f"http://api.scraperapi.com"
        f"?api_key={SCRAPER_API_KEY}"
        f"&url={target_url}"
        f"&country_code={country}"
        f"&render=false"
    )


def extract_text_blocks(html: str, min_len: int = 20) -> list:
    """Extract all meaningful text blocks from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()
    blocks = []
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "li", "span", "div", "td", "a"]):
        text = tag.get_text(separator=" ", strip=True)
        if len(text) >= min_len and text not in blocks:
            blocks.append(text)
    return blocks[:50]


def company_mentioned(text_blocks: list, query: str) -> bool:
    """Check if any variation of the company name appears in text."""
    query_words = [w.lower() for w in query.split() if len(w) > 2]
    for block in text_blocks:
        block_lower = block.lower()
        if any(word in block_lower for word in query_words):
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
        if isinstance(val, Exception):
            results[key] = {"error": str(val), "source": key}
        else:
            results[key] = val

    return results


# ── GOOGLE (direct) ───────────────────────────────────────────────────────────

async def _google_reviews(query: str) -> dict:
    return await _google_search(f"{query} reviews India supplier", "Google Reviews")


async def _google_fraud(query: str) -> dict:
    data = await _google_search(f"{query} fraud scam fake complaints India", "Google Fraud Check")
    fraud_keywords = ["fraud", "scam", "fake", "cheated", "complaint", "loss", "beware", "warning", "cheat"]
    snippets = data.get("snippets", [])
    flags = [s for s in snippets if any(kw in s.lower() for kw in fraud_keywords)]
    data["fraud_mentions"] = len(flags)
    data["fraud_snippets"] = flags[:3]
    return data


async def _google_complaints(query: str) -> dict:
    data = await _google_search(f"{query} complaint consumer forum India", "Google Complaints")
    complaint_keywords = ["complaint", "issue", "problem", "refund", "cheated", "not delivered", "poor quality"]
    snippets = data.get("snippets", [])
    flags = [s for s in snippets if any(kw in s.lower() for kw in complaint_keywords)]
    data["complaint_count"] = len(flags)
    data["complaint_snippets"] = flags[:3]
    return data


async def _google_search(query: str, source_name: str) -> dict:
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10&hl=en"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            snippets = []
            for tag in soup.find_all(["div", "span", "p"]):
                text = tag.get_text(separator=" ", strip=True)
                if 40 < len(text) < 500 and text not in snippets:
                    snippets.append(text)
            links = []
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if href.startswith("/url?q="):
                    real = href.split("/url?q=")[1].split("&")[0]
                    if real.startswith("http") and "google" not in real:
                        links.append(real)
            return {
                "source": source_name,
                "snippets": snippets[:8],
                "links": links[:5],
            }
    except Exception as e:
        return {"source": source_name, "snippets": [], "error": str(e)}


# ── INDIAMART ─────────────────────────────────────────────────────────────────

async def _indiamart(query: str) -> dict:
    target = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target))
            blocks = extract_text_blocks(resp.text)
            found = company_mentioned(blocks, query)

            # Look for rating patterns like "4.5", "★", "reviews"
            ratings = [b for b in blocks if any(x in b.lower() for x in ["★", "rating", "review", "stars"]) and len(b) < 100]
            # Look for year patterns
            years = [b for b in blocks if re.search(r'(since|est\.?|established|year)\s*\d{4}', b.lower())]
            # Look for verified patterns
            verified = [b for b in blocks if any(x in b.lower() for x in ["verified", "trust", "gst verified"])]
            # Extract company-like names (capitalized phrases)
            companies = [b for b in blocks if b[0].isupper() and len(b) < 80 and len(b) > 5][:5]

            return {
                "source": "IndiaMART",
                "companies_found": companies[:3],
                "ratings": ratings[:3],
                "years_listed": years[:2],
                "verified_count": len(verified),
                "found": found or len(companies) > 0,
                "raw_blocks": blocks[:10],
            }
    except Exception as e:
        return {"source": "IndiaMART", "error": str(e), "found": False}


# ── TRADEINDIA ────────────────────────────────────────────────────────────────

async def _tradeindia(query: str) -> dict:
    target = f"https://www.tradeindia.com/search/?q={query.replace(' ', '+')}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target))
            blocks = extract_text_blocks(resp.text)
            found = company_mentioned(blocks, query)
            verified = [b for b in blocks if "verified" in b.lower()]
            companies = [b for b in blocks if b[0].isupper() and 5 < len(b) < 80][:5]

            return {
                "source": "TradeIndia",
                "companies_found": companies[:3],
                "verified_count": len(verified),
                "found": found or len(companies) > 0,
                "raw_blocks": blocks[:10],
            }
    except Exception as e:
        return {"source": "TradeIndia", "error": str(e), "found": False}


# ── JUSTDIAL ──────────────────────────────────────────────────────────────────

async def _justdial(query: str) -> dict:
    target = f"https://www.justdial.com/search?q={query.replace(' ', '+')}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target))
            blocks = extract_text_blocks(resp.text)
            found = company_mentioned(blocks, query)
            ratings = [b for b in blocks if any(x in b for x in ["★", "Rated", "Rating", "/5"]) and len(b) < 100]
            businesses = [b for b in blocks if b[0].isupper() and 5 < len(b) < 80][:5]

            return {
                "source": "Justdial",
                "businesses_found": businesses[:3],
                "ratings": ratings[:3],
                "found": found or len(businesses) > 0,
                "raw_blocks": blocks[:10],
            }
    except Exception as e:
        return {"source": "Justdial", "error": str(e), "found": False}


# ── MCA PORTAL ────────────────────────────────────────────────────────────────

async def _mca_portal(query: str) -> dict:
    target = f"https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do?companyName={query.replace(' ', '+')}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target))
            blocks = extract_text_blocks(resp.text)
            found = company_mentioned(blocks, query)

            # Look for CIN pattern (21 char alphanumeric)
            cin_pattern = re.compile(r'[A-Z]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}')
            cin_matches = []
            for block in blocks:
                match = cin_pattern.search(block)
                if match:
                    cin_matches.append(match.group())

            # Look for status keywords
            status_blocks = [b for b in blocks if any(x in b.lower() for x in ["active", "strike off", "dissolved", "amalgamated"])]
            # Look for date patterns
            date_blocks = [b for b in blocks if re.search(r'\d{2}/\d{2}/\d{4}', b)]

            company_data = {}
            if found:
                company_data = {
                    "name": query,
                    "cin": cin_matches[0] if cin_matches else "N/A",
                    "status": status_blocks[0] if status_blocks else "Found on MCA",
                    "incorporation_date": date_blocks[0] if date_blocks else "N/A",
                    "type": "N/A",
                    "state": "N/A",
                }

            return {
                "source": "MCA Portal",
                "companies": [company_data] if company_data else [],
                "found": found or len(cin_matches) > 0,
                "raw_blocks": blocks[:10],
            }
    except Exception as e:
        return {"source": "MCA Portal", "error": str(e), "found": False}


# ── ZAUBA CORP ────────────────────────────────────────────────────────────────

async def _zauba_corp(query: str) -> dict:
    target = f"https://www.zaubacorp.com/company-search/{query.replace(' ', '-').upper()}"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target))
            blocks = extract_text_blocks(resp.text)
            found = company_mentioned(blocks, query)

            cin_pattern = re.compile(r'[A-Z]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}')
            companies = []
            for block in blocks:
                if cin_pattern.search(block) or (query.split()[0].lower() in block.lower() and len(block) < 100):
                    companies.append({"name": block[:80], "cin": "N/A", "status": "N/A", "incorporation": "N/A"})

            return {
                "source": "Zauba Corp",
                "companies": companies[:3],
                "found": found or len(companies) > 0,
            }
    except Exception as e:
        return {"source": "Zauba Corp", "error": str(e), "found": False}


# ── LINKEDIN (via Google) ─────────────────────────────────────────────────────

async def _linkedin_presence(query: str) -> dict:
    search_url = f"https://www.google.com/search?q=site:linkedin.com+%22{query.replace(' ', '+')}%22+India"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(search_url)
            soup = BeautifulSoup(resp.text, "html.parser")

            linkedin_links = []
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if "/url?q=" in href:
                    real = href.split("/url?q=")[1].split("&")[0]
                    if "linkedin.com" in real:
                        linkedin_links.append(real)

            snippets = []
            for tag in soup.find_all(["div", "span"]):
                text = tag.get_text(separator=" ", strip=True)
                if "linkedin" in text.lower() and 20 < len(text) < 300:
                    snippets.append(text)

            # Also check if query words appear in any result
            all_text = soup.get_text().lower()
            query_words = [w.lower() for w in query.split() if len(w) > 2]
            name_found = any(word in all_text for word in query_words)

            return {
                "source": "LinkedIn",
                "profile_found": len(linkedin_links) > 0 or name_found,
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
        f"{query} cheated supplier",
    ]
    all_snippets = []
    all_flags = []
    fraud_keywords = ["scam", "fraud", "fake", "cheat", "complaint", "beware",
                      "warning", "not genuine", "money lost", "not delivered"]
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            for q in queries:
                url = f"https://www.google.com/search?q={q.replace(' ', '+')}&num=5"
                resp = await client.get(url)
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup.find_all(["div", "span", "p"]):
                    text = tag.get_text(separator=" ", strip=True)
                    if len(text) > 30:
                        all_snippets.append(text)
                        if any(kw in text.lower() for kw in fraud_keywords):
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

        url = scraper_url(target_url)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            result["accessible"] = resp.status_code == 200
            result["status_code"] = resp.status_code
            blocks = extract_text_blocks(resp.text)
            all_text = " ".join(blocks).lower()

            result["has_contact_info"] = any(kw in all_text for kw in ["contact", "phone", "email", "call us", "reach us"])
            result["has_address"] = any(kw in all_text for kw in ["address", "location", "office", "headquarter", "plot", "sector"])
            result["has_about_page"] = any(kw in all_text for kw in ["about us", "our company", "who we are", "our story"])
            result["has_product_catalog"] = any(kw in all_text for kw in ["product", "catalogue", "catalog", "price list"])

            if not result["has_contact_info"]:
                result["flags"].append("No contact information found on website")
            if not result["has_address"]:
                result["flags"].append("No physical address found on website")

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
                            result["flags"].append(f"Domain created very recently — high risk")
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