"""
Verifii Scraper — Multi-source supplier research
Uses ScraperAPI for Indian sites that geo-block non-Indian IPs.
Uses direct requests for Google (works fine from Render).
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
    """Wrap a URL through ScraperAPI with Indian IP."""
    return (
        f"http://api.scraperapi.com"
        f"?api_key={SCRAPER_API_KEY}"
        f"&url={target_url}"
        f"&country_code={country}"
        f"&render=false"
    )


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


# ── GOOGLE (direct — works fine from Render) ─────────────────────────────────

async def _google_reviews(query: str) -> dict:
    return await _google_search(f"{query} reviews India supplier", "Google Reviews")


async def _google_fraud(query: str) -> dict:
    data = await _google_search(f"{query} fraud scam fake", "Google Fraud Check")
    fraud_keywords = ["fraud", "scam", "fake", "cheated", "complaint", "loss", "beware", "warning"]
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
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            snippets = []
            for tag in soup.select("div.BNeawe, div.VwiC3b, span.aCOpRe, div.IsZvec"):
                text = tag.get_text(separator=" ", strip=True)
                if text and len(text) > 30:
                    snippets.append(text)
            links = []
            for a in soup.select("a[href]")[:10]:
                href = a.get("href", "")
                if href.startswith("/url?q="):
                    real = href.split("/url?q=")[1].split("&")[0]
                    if real.startswith("http"):
                        links.append(real)
            return {"source": source_name, "snippets": snippets[:6], "links": links[:5]}
    except Exception as e:
        return {"source": source_name, "snippets": [], "error": str(e)}


# ── INDIAMART (via ScraperAPI — Indian IP) ────────────────────────────────────

async def _indiamart(query: str) -> dict:
    target = f"https://dir.indiamart.com/search.mp?ss={query.replace(' ', '+')}"
    url = scraper_url(target)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            companies = []
            for card in soup.select(".companyname, .company-name, .bname, .ib-heading, h2.name")[:5]:
                name = card.get_text(strip=True)
                if name:
                    companies.append(name)

            ratings = []
            for r in soup.select(".rating, .star-rating, .impRating")[:5]:
                ratings.append(r.get_text(strip=True))

            years = []
            for y in soup.select(".established, .year, .impYear")[:5]:
                years.append(y.get_text(strip=True))

            verified = soup.select(".verified, .trust-seal, .impVerified")

            return {
                "source": "IndiaMART",
                "companies_found": companies,
                "ratings": ratings,
                "years_listed": years,
                "verified_count": len(verified),
                "found": len(companies) > 0,
            }
    except Exception as e:
        return {"source": "IndiaMART", "error": str(e), "found": False}


# ── TRADEINDIA (via ScraperAPI) ───────────────────────────────────────────────

async def _tradeindia(query: str) -> dict:
    target = f"https://www.tradeindia.com/search/?q={query.replace(' ', '+')}"
    url = scraper_url(target)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            companies = []
            for card in soup.select(".company-name, .company_name, h2.name, .compName")[:5]:
                name = card.get_text(strip=True)
                if name:
                    companies.append(name)

            verified = soup.select(".verified, .trust-icon, .verified-badge")

            return {
                "source": "TradeIndia",
                "companies_found": companies,
                "verified_count": len(verified),
                "found": len(companies) > 0,
            }
    except Exception as e:
        return {"source": "TradeIndia", "error": str(e), "found": False}


# ── JUSTDIAL (via ScraperAPI) ─────────────────────────────────────────────────

async def _justdial(query: str) -> dict:
    target = f"https://www.justdial.com/search?q={query.replace(' ', '+')}&nc=cat"
    url = scraper_url(target)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            businesses = []
            for item in soup.select(".resultbox_title_anchor, .store-name, .fn")[:5]:
                name = item.get_text(strip=True)
                if name:
                    businesses.append(name)

            ratings = []
            for r in soup.select(".ratingCount, .rating_count, .star_m")[:5]:
                ratings.append(r.get_text(strip=True))

            return {
                "source": "Justdial",
                "businesses_found": businesses,
                "ratings": ratings,
                "found": len(businesses) > 0,
            }
    except Exception as e:
        return {"source": "Justdial", "error": str(e), "found": False}


# ── MCA PORTAL (via ScraperAPI) ──────────────────────────────────────────────

async def _mca_portal(query: str) -> dict:
    target = f"https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do?companyName={query.replace(' ', '+')}"
    url = scraper_url(target)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            company_data = {}
            rows = soup.select("table tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(strip=True)
                    if "company name" in label:
                        company_data["name"] = value
                    elif "status" in label:
                        company_data["status"] = value
                    elif "incorporation" in label:
                        company_data["incorporation_date"] = value
                    elif "type" in label:
                        company_data["type"] = value
                    elif "cin" in label:
                        company_data["cin"] = value

            # Try MCA API endpoint
            if not company_data:
                api_target = f"https://efiling.mca.gov.in/efs-filing/rest/getCompanyINC/getCompanyDetails?companyName={query.replace(' ', '%20')}"
                api_url = scraper_url(api_target)
                resp2 = await client.get(api_url)
                try:
                    data = resp2.json()
                    companies = data if isinstance(data, list) else [data]
                    results = []
                    for c in companies[:3]:
                        results.append({
                            "name": c.get("companyName", "N/A"),
                            "cin": c.get("cin", "N/A"),
                            "status": c.get("companyStatus", "N/A"),
                            "incorporation_date": c.get("dateOfIncorporation", "N/A"),
                            "type": c.get("companyType", "N/A"),
                            "state": c.get("registeredState", "N/A"),
                        })
                    if results:
                        return {"source": "MCA Portal", "companies": results, "found": True}
                except Exception:
                    pass

            return {
                "source": "MCA Portal",
                "companies": [company_data] if company_data else [],
                "found": bool(company_data),
            }
    except Exception as e:
        return {"source": "MCA Portal", "error": str(e), "found": False}


# ── ZAUBA CORP (via ScraperAPI) ───────────────────────────────────────────────

async def _zauba_corp(query: str) -> dict:
    target = f"https://www.zaubacorp.com/company-search/{query.replace(' ', '-').upper()}"
    url = scraper_url(target)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            companies = []
            for row in soup.select("table tbody tr, .company-row")[:5]:
                cells = row.find_all("td")
                if len(cells) >= 3:
                    companies.append({
                        "name": cells[0].get_text(strip=True),
                        "cin": cells[1].get_text(strip=True) if len(cells) > 1 else "N/A",
                        "status": cells[2].get_text(strip=True) if len(cells) > 2 else "N/A",
                        "incorporation": cells[3].get_text(strip=True) if len(cells) > 3 else "N/A",
                    })

            return {
                "source": "Zauba Corp",
                "companies": companies,
                "found": len(companies) > 0,
            }
    except Exception as e:
        return {"source": "Zauba Corp", "error": str(e), "found": False}


# ── LINKEDIN (via Google — no ScraperAPI needed) ──────────────────────────────

async def _linkedin_presence(query: str) -> dict:
    search_url = f"https://www.google.com/search?q=site:linkedin.com+{query.replace(' ', '+')}+company+India"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(search_url)
            soup = BeautifulSoup(resp.text, "html.parser")

            linkedin_links = []
            snippets = []
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if "linkedin.com/company" in href or "linkedin.com/in" in href:
                    linkedin_links.append(href)
            for tag in soup.select("div.BNeawe, div.VwiC3b"):
                text = tag.get_text(strip=True)
                if "linkedin" in text.lower() and len(text) > 20:
                    snippets.append(text)

            return {
                "source": "LinkedIn",
                "profile_found": len(linkedin_links) > 0,
                "links": linkedin_links[:3],
                "snippets": snippets[:3],
            }
    except Exception as e:
        return {"source": "LinkedIn", "profile_found": False, "error": str(e)}


# ── SCAM DATABASES (via Google — works fine) ──────────────────────────────────

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
                for tag in soup.select("div.BNeawe, div.VwiC3b"):
                    text = tag.get_text(strip=True)
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


# ── WEBSITE ANALYSIS (via ScraperAPI) ────────────────────────────────────────

async def _website_analysis(target_url: str) -> dict:
    if not target_url.startswith("http"):
        target_url = "https://" + target_url

    result = {
        "source": "Website Analysis",
        "url": target_url,
        "accessible": False,
        "has_contact_info": False,
        "has_address": False,
        "has_professional_email": False,
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

            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True).lower()

            result["has_contact_info"] = any(kw in text for kw in ["contact", "phone", "email", "call us"])
            result["has_address"] = any(kw in text for kw in ["address", "location", "office", "headquarter"])
            result["has_about_page"] = any(kw in text for kw in ["about us", "our company", "who we are"])
            result["has_product_catalog"] = any(kw in text for kw in ["product", "catalogue", "catalog", "price list"])

            if not result["has_contact_info"]:
                result["flags"].append("No contact information found on website")
            if not result["has_address"]:
                result["flags"].append("No physical address found on website")
            if not result["has_about_page"]:
                result["flags"].append("No 'About Us' page found")

        # WHOIS domain age
        try:
            whois_url = f"https://api.whois.vu/?q={domain}&format=json"
            async with httpx.AsyncClient(timeout=8) as client:
                whois_resp = await client.get(whois_url)
                whois_data = whois_resp.json()
                creation = whois_data.get("created", "") or whois_data.get("creation_date", "")
                if creation:
                    result["domain_creation_date"] = creation
                    try:
                        created_year = int(str(creation)[:4])
                        age_years = datetime.now().year - created_year
                        result["domain_age_years"] = age_years
                        if age_years < 1:
                            result["flags"].append(f"Domain created very recently ({creation}) — high risk")
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
    free_providers = [
        "gmail.com", "yahoo.com", "yahoo.in", "hotmail.com",
        "outlook.com", "rediffmail.com", "ymail.com"
    ]
    result = {
        "source": "Email Domain Check",
        "email": email,
        "flags": [],
    }
    if "@" not in email:
        result["flags"].append("Invalid email format")
        result["is_professional"] = False
        return result

    domain = email.split("@")[-1].lower()
    result["domain"] = domain
    result["is_professional"] = domain not in free_providers

    if not result["is_professional"]:
        result["flags"].append(
            f"Supplier using free email ({domain}) instead of company domain — red flag for B2B"
        )
    else:
        result["flags"].append(f"Professional company email domain: {domain}")

    return result