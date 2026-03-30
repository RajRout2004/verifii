import httpx
import re
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://services.gst.gov.in/services/searchtp",
}

STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra & Nagar Haveli and Daman & Diu", "27": "Maharashtra",
    "28": "Andhra Pradesh (old)", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman & Nicobar", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh",
}

GSTIN_PATTERN = re.compile(r'\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b')


def scraper_url(target_url: str, country: str = "in", render: bool = False) -> str:
    render_str = "true" if render else "false"
    return (
        f"http://api.scraperapi.com"
        f"?api_key={SCRAPER_API_KEY}"
        f"&url={target_url}"
        f"&country_code={country}"
        f"&render={render_str}"
    )


def get_state_from_gstin(gstin: str) -> str:
    code = gstin[:2] if len(gstin) >= 2 else ""
    return STATE_CODES.get(code, "Unknown State")


def is_valid_gstin_format(gstin: str) -> bool:
    return bool(GSTIN_PATTERN.match(gstin.upper()))


async def lookup_gstin(gstin: str) -> dict:
    """Look up a specific GSTIN."""
    gstin = gstin.strip().upper()

    # Method 1: Official GST portal (may be blocked by WAF)
    result = await _try_gst_gov_api(gstin)
    if result.get("valid"):
        return result

    # Method 2: Google search for this specific GSTIN to find cached details
    result = await _try_google_gstin_lookup(gstin)
    if result.get("valid"):
        return result

    # Fallback: format validation + state decode
    return _validate_format_only(gstin)


async def search_gstin_by_name(company_name: str) -> dict:
    """Search all GSTINs for a company name — combines multiple sources."""
    results = []
    seen_gstins = set()

    # Method 1: GST portal API (usually blocked, but try anyway)
    try:
        url = f"https://services.gst.gov.in/services/api/search/taxpayerDetails?tradeName={company_name.replace(' ', '%20')}"
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data[:20]:
                            gstin = item.get("gstin", "")
                            if gstin and is_valid_gstin_format(gstin) and gstin not in seen_gstins:
                                seen_gstins.add(gstin)
                                results.append({
                                    "gstin": gstin,
                                    "legal_name": item.get("lgnm", "N/A"),
                                    "trade_name": item.get("tradeNam", "N/A"),
                                    "state": get_state_from_gstin(gstin),
                                    "state_code": gstin[:2],
                                    "status": item.get("sts", "N/A"),
                                    "registration_date": item.get("rgdt", "N/A"),
                                    "business_type": item.get("dty", "N/A"),
                                })
                except Exception:
                    pass
    except Exception:
        pass

    # Method 2: Google search for GSTINs via ScraperAPI (most reliable)
    if not results:
        google_gstins = await _google_gstin_search(company_name)
        for gstin in google_gstins:
            if gstin not in seen_gstins:
                seen_gstins.add(gstin)
                # Try to get details for each GSTIN
                details = await _try_gst_gov_api(gstin)
                if details.get("valid"):
                    results.append({
                        "gstin": gstin,
                        "legal_name": details.get("legal_name", "N/A"),
                        "trade_name": details.get("trade_name", "N/A"),
                        "state": get_state_from_gstin(gstin),
                        "state_code": gstin[:2],
                        "status": details.get("status", "N/A"),
                        "registration_date": details.get("registration_date", "N/A"),
                        "business_type": details.get("business_type", "N/A"),
                    })
                else:
                    results.append({
                        "gstin": gstin,
                        "legal_name": "N/A",
                        "trade_name": company_name.upper(),
                        "state": get_state_from_gstin(gstin),
                        "state_code": gstin[:2],
                        "status": "Found via web search",
                        "registration_date": "N/A",
                        "business_type": "N/A",
                    })

    # Method 3: Google search on GST directory sites
    if len(results) < 3:
        site_gstins = await _google_gstin_site_search(company_name)
        for gstin in site_gstins:
            if gstin not in seen_gstins:
                seen_gstins.add(gstin)
                results.append({
                    "gstin": gstin,
                    "legal_name": "N/A",
                    "trade_name": company_name.upper(),
                    "state": get_state_from_gstin(gstin),
                    "state_code": gstin[:2],
                    "status": "Found via web search",
                    "registration_date": "N/A",
                    "business_type": "N/A",
                })

    # Sort by state code for clean display
    results.sort(key=lambda x: x.get("state_code", "99"))

    return {
        "company_name": company_name,
        "total_found": len(results),
        "gstins": results[:20],
        "note": f"Found {len(results)} GSTIN registrations across India" if results else "No GSTINs found — try entering GSTIN directly or use the full legal company name",
    }


# ── GST Portal Direct API ─────────────────────────────────────────────────────

async def _try_gst_gov_api(gstin: str) -> dict:
    """Try official GST portal API. Often blocked by WAF."""
    url = f"https://services.gst.gov.in/services/api/search/taxpayerDetails?gstin={gstin}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                # Check for WAF block
                if "Request Rejected" in resp.text:
                    return {"valid": False}
                data = resp.json()
                if data.get("sts") or data.get("lgnm"):
                    return {
                        "valid": True,
                        "gstin": gstin,
                        "legal_name": data.get("lgnm", "N/A"),
                        "trade_name": data.get("tradeNam", "N/A"),
                        "status": data.get("sts", "N/A"),
                        "state": get_state_from_gstin(gstin),
                        "state_code": gstin[:2],
                        "registration_date": data.get("rgdt", "N/A"),
                        "business_type": data.get("dty", "N/A"),
                        "source": "GST Gov API",
                    }
    except Exception:
        pass
    return {"valid": False}


# ── Google-based GSTIN Discovery (via ScraperAPI) ──────────────────────────────

async def _google_gstin_search(company_name: str) -> list:
    """Search Google for '{company} GSTIN number India' and extract GSTINs from results."""
    if not SCRAPER_API_KEY:
        return []

    gstins_found = set()
    query = f'"{company_name}" GSTIN number India'
    target = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10&hl=en&gl=in"

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target, country="in"))
            if resp.status_code == 200:
                # Extract all valid GSTIN patterns from the page
                found = GSTIN_PATTERN.findall(resp.text)
                for gstin in found:
                    if is_valid_gstin_format(gstin):
                        gstins_found.add(gstin)
    except Exception:
        pass

    return list(gstins_found)[:15]


async def _google_gstin_site_search(company_name: str) -> list:
    """Search Google on GST directory sites for company GSTINs."""
    if not SCRAPER_API_KEY:
        return []

    gstins_found = set()
    query = f'"{company_name}" GSTIN site:knowyourgst.com OR site:gstzen.in OR site:mastersindia.com OR site:cleartax.in'
    target = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10&hl=en&gl=in"

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target, country="in"))
            if resp.status_code == 200:
                found = GSTIN_PATTERN.findall(resp.text)
                for gstin in found:
                    if is_valid_gstin_format(gstin):
                        gstins_found.add(gstin)
    except Exception:
        pass

    return list(gstins_found)[:10]


async def _try_google_gstin_lookup(gstin: str) -> dict:
    """Look up a specific GSTIN via Google to find cached registration details."""
    if not SCRAPER_API_KEY:
        return {"valid": False}

    target = f"https://www.google.com/search?q=GSTIN+{gstin}&hl=en&gl=in"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(scraper_url(target, country="in"))
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                page_text = soup.get_text()

                # Try to extract legal name from search results
                legal_name = "N/A"
                trade_name = "N/A"
                status = "N/A"

                # Common patterns in Google snippets about GSTINs
                name_patterns = [
                    re.compile(r'(?:Legal\s*Name|Taxpayer\s*Name)\s*[:\-]\s*([A-Z][A-Z\s&.,]+)', re.IGNORECASE),
                    re.compile(r'(?:Trade\s*Name)\s*[:\-]\s*([A-Z][A-Z\s&.,]+)', re.IGNORECASE),
                ]
                status_pattern = re.compile(r'(?:Status)\s*[:\-]\s*(Active|Inactive|Cancelled|Suspended)', re.IGNORECASE)

                for pattern in name_patterns:
                    match = pattern.search(page_text)
                    if match:
                        name = match.group(1).strip()
                        if len(name) > 3 and len(name) < 100:
                            if legal_name == "N/A":
                                legal_name = name
                            else:
                                trade_name = name

                status_match = status_pattern.search(page_text)
                if status_match:
                    status = status_match.group(1).capitalize()

                if legal_name != "N/A":
                    return {
                        "valid": True,
                        "gstin": gstin,
                        "legal_name": legal_name,
                        "trade_name": trade_name,
                        "status": status,
                        "state": get_state_from_gstin(gstin),
                        "state_code": gstin[:2],
                        "registration_date": "N/A",
                        "business_type": "N/A",
                        "source": "Google (cached)",
                    }
    except Exception:
        pass
    return {"valid": False}


# ── Format-only Validation (final fallback) ────────────────────────────────────

def _validate_format_only(gstin: str) -> dict:
    valid_format = is_valid_gstin_format(gstin)
    state = get_state_from_gstin(gstin)
    pan = gstin[2:12] if len(gstin) >= 12 else ""
    return {
        "valid": valid_format,
        "gstin": gstin,
        "legal_name": "Could not fetch from registry",
        "trade_name": "N/A",
        "status": "Format valid — live data unavailable" if valid_format else "Invalid GSTIN format",
        "state": state,
        "state_code": gstin[:2],
        "registration_date": "N/A",
        "business_type": "N/A",
        "pan": pan,
        "source": "Format validation only",
        "note": "GSTIN format is valid. GST registry APIs are rate-limited." if valid_format else "Invalid GSTIN format.",
    }