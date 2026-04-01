import asyncio
import httpx
import re
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from scraper import scraper_semaphore

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

# Reduced timeouts for individual HTTP calls
GST_API_TIMEOUT = 8
SCRAPER_TIMEOUT = 12
# Max GSTINs to look up details for (higher since we filter by name match)
MAX_GSTIN_DETAIL_LOOKUPS = 10


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
    gstin = gstin.upper().strip()
    if not GSTIN_PATTERN.match(gstin):
        return False
    # Check for obvious dummy/example GSTINs used on blog posts/directories
    invalid_patterns = ["AAAAA", "0000", "1234", "9999", "1111", "ABCDE", "XXXXX"]
    if any(p in gstin for p in invalid_patterns):
        return False
    # Ensure 4th char of PAN is valid (C, P, H, F, A, T, B, L, J, G)
    pan = gstin[2:12]
    if len(pan) == 10 and pan[3] not in 'CPHFATBLJG':
        return False
    return True


async def lookup_gstin(gstin: str) -> dict:
    """Look up a specific GSTIN — tries GST API and Google in PARALLEL."""
    gstin = gstin.strip().upper()

    # Run both methods in parallel, take the first valid result
    api_task = asyncio.create_task(_try_gst_gov_api(gstin))
    google_task = asyncio.create_task(_try_google_gstin_lookup(gstin))

    results = await asyncio.gather(api_task, google_task, return_exceptions=True)

    # Prefer GST API result if valid, then Google, then format fallback
    for r in results:
        if isinstance(r, dict) and r.get("valid"):
            return r

    # Fallback: format validation + state decode
    return _validate_format_only(gstin)


def _name_matches_company(registered_name: str, search_query: str) -> bool:
    """Check if a GSTIN's registered name plausibly matches the company being searched.
    
    This prevents collecting random GSTINs that appear on Google results pages
    but belong to completely unrelated companies.
    """
    if not registered_name or registered_name in ("N/A", "Could not fetch from registry", ""):
        return False

    # Normalize both strings: lowercase, strip common suffixes, remove punctuation
    def normalize(s):
        s = s.lower().strip()
        # Remove common company suffixes
        for suffix in [" private limited", " pvt ltd", " pvt. ltd.", " pvt. ltd",
                       " limited", " ltd", " ltd.", " llp", " inc", " inc.",
                       " technologies", " technology", " tech", " solutions",
                       " services", " india", " enterprises", " infra",
                       " consultants", " consulting", " international"]:
            s = s.replace(suffix, "")
        # Remove punctuation and extra whitespace
        s = re.sub(r'[^a-z0-9\s]', '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    norm_registered = normalize(registered_name)
    norm_query = normalize(search_query)

    if not norm_registered or not norm_query:
        return False

    # Exact match after normalization
    if norm_registered == norm_query:
        return True

    # One contains the other
    if norm_query in norm_registered or norm_registered in norm_query:
        return True

    # Word-level overlap: check if the core query words appear in the registered name
    query_words = [w for w in norm_query.split() if len(w) > 2]
    reg_words = set(norm_registered.split())

    if not query_words:
        return False

    # At least the primary word of the query must appear
    matching_words = sum(1 for w in query_words if w in reg_words)
    # For single-word company names (like "aionos"), require exact word match
    if len(query_words) == 1:
        return query_words[0] in reg_words
    # For multi-word names, require majority match
    return matching_words >= max(1, len(query_words) * 0.6)


async def search_gstin_by_name(company_name: str) -> dict:
    """Search all GSTINs for a company name — runs sources in PARALLEL with tight timeouts.
    
    CRITICAL: Every GSTIN found via Google is verified against the GST registry to confirm
    its registered name matches the searched company. This prevents returning GSTINs from
    unrelated companies that just happen to appear on the same Google results page.
    """
    results = []
    seen_gstins = set()

    # Run ALL discovery methods in parallel
    tasks = [
        _search_gst_portal(company_name),
        _google_gstin_search(company_name),
        _google_gstin_site_search(company_name),
    ]
    task_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process GST portal results — these are already name-matched by the portal itself
    portal_results = task_results[0]
    if isinstance(portal_results, list):
        for item in portal_results:
            gstin = item.get("gstin", "")
            if gstin and gstin not in seen_gstins:
                # Portal results have names from the API — verify they match
                legal = item.get("legal_name", "")
                trade = item.get("trade_name", "")
                if _name_matches_company(legal, company_name) or _name_matches_company(trade, company_name):
                    seen_gstins.add(gstin)
                    results.append(item)

    # Collect GSTINs from Google searches
    # Each search returns a dict with 'all' (all GSTINs) and 'contextual' (GSTINs near company name)
    google_gstins = set()
    contextual_gstins = set()  # GSTINs found near the company name — higher confidence
    for r in task_results[1:]:
        if isinstance(r, dict) and not isinstance(r, Exception):
            google_gstins.update(r.get("all", []))
            contextual_gstins.update(r.get("contextual", []))
        elif isinstance(r, list):
            google_gstins.update(r)

    # For Google-found GSTINs, look up details and VERIFY the registered name matches
    new_gstins = [g for g in google_gstins if g not in seen_gstins]
    if new_gstins:
        # Limit the number of detail lookups to prevent timeout cascade
        gstins_to_lookup = new_gstins[:MAX_GSTIN_DETAIL_LOOKUPS]
        detail_tasks = [_try_gst_gov_api(g) for g in gstins_to_lookup]
        try:
            detail_results = await asyncio.wait_for(
                asyncio.gather(*detail_tasks, return_exceptions=True),
                timeout=GST_API_TIMEOUT + 2,
            )
        except asyncio.TimeoutError:
            detail_results = [{"valid": False}] * len(gstins_to_lookup)

        # Collect GSTINs that need Google-based fallback verification
        needs_google_verify = []

        for gstin, details in zip(gstins_to_lookup, detail_results):
            seen_gstins.add(gstin)
            if isinstance(details, dict) and details.get("valid"):
                legal = details.get("legal_name", "N/A")
                trade = details.get("trade_name", "N/A")
                # ONLY include if the registered name actually matches the company
                if _name_matches_company(legal, company_name) or _name_matches_company(trade, company_name):
                    results.append({
                        "gstin": gstin,
                        "legal_name": legal,
                        "trade_name": trade,
                        "state": get_state_from_gstin(gstin),
                        "state_code": gstin[:2],
                        "status": details.get("status", "N/A"),
                        "registration_date": details.get("registration_date", "N/A"),
                        "business_type": details.get("business_type", "N/A"),
                    })
            else:
                # GST API failed (WAF blocked) — try Google-based verification as fallback
                # But only for GSTINs found in contextual snippets (not random page GSTINs)
                if gstin in contextual_gstins:
                    needs_google_verify.append(gstin)

        # Fallback: verify unresolved GSTINs via Google cached data
        if needs_google_verify:
            google_tasks = [_try_google_gstin_lookup(g) for g in needs_google_verify[:3]]
            try:
                google_results = await asyncio.wait_for(
                    asyncio.gather(*google_tasks, return_exceptions=True),
                    timeout=SCRAPER_TIMEOUT + 2,
                )
            except asyncio.TimeoutError:
                google_results = [{"valid": False}] * len(needs_google_verify[:3])

            for gstin, gdetails in zip(needs_google_verify[:3], google_results):
                if isinstance(gdetails, dict) and gdetails.get("valid"):
                    legal = gdetails.get("legal_name", "N/A")
                    trade = gdetails.get("trade_name", "N/A")
                    if _name_matches_company(legal, company_name) or _name_matches_company(trade, company_name):
                        results.append({
                            "gstin": gstin,
                            "legal_name": legal,
                            "trade_name": trade,
                            "state": get_state_from_gstin(gstin),
                            "state_code": gstin[:2],
                            "status": gdetails.get("status", "N/A"),
                            "registration_date": gdetails.get("registration_date", "N/A"),
                            "business_type": gdetails.get("business_type", "N/A"),
                        })

        # Do NOT add remaining GSTINs beyond lookup limit without verification.
        # Adding unverified GSTINs is what caused the original bug.

    # Sort by state code for clean display
    results.sort(key=lambda x: x.get("state_code", "99"))

    return {
        "company_name": company_name,
        "total_found": len(results),
        "gstins": results[:20],
        "note": f"Found {len(results)} verified GSTIN registrations for {company_name}" if results else "No GSTINs found — try entering GSTIN directly or use the full legal company name",
    }


# ── GST Portal Direct API ─────────────────────────────────────────────────────

async def _search_gst_portal(company_name: str) -> list:
    """Try GST portal API for name search. Usually blocked, but fast to fail."""
    results = []
    url = f"https://services.gst.gov.in/services/api/search/taxpayerDetails?tradeName={company_name.replace(' ', '%20')}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=GST_API_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data[:20]:
                            gstin = item.get("gstin", "")
                            if gstin and is_valid_gstin_format(gstin):
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
    return results


async def _try_gst_gov_api(gstin: str) -> dict:
    """Try official GST portal API. Often blocked by WAF."""
    url = f"https://services.gst.gov.in/services/api/search/taxpayerDetails?gstin={gstin}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=GST_API_TIMEOUT, follow_redirects=True) as client:
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

async def _google_gstin_search(company_name: str) -> dict:
    """Search Google for '{company} GSTIN number India' and extract GSTINs from results.
    
    Returns a dict with:
      - 'all': all GSTINs found on the page
      - 'contextual': GSTINs found in text blocks that also mention the company name
    """
    if not SCRAPER_API_KEY:
        return {"all": [], "contextual": []}

    all_gstins = set()
    contextual_gstins = set()
    query = f'"{company_name}" GSTIN number India'
    target = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10&hl=en&gl=in"
    company_words = [w.lower() for w in company_name.split() if len(w) > 2]

    try:
        async with scraper_semaphore:
            async with httpx.AsyncClient(timeout=SCRAPER_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(scraper_url(target, country="in"))
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for tag in soup.find_all(["div", "span", "p", "li", "td", "a", "h3"]):
                        block_text = tag.get_text(separator=" ", strip=True)
                        if len(block_text) < 15 or len(block_text) > 500:
                            continue
                        found = GSTIN_PATTERN.findall(block_text)
                        block_lower = block_text.lower()
                        has_company = any(w in block_lower for w in company_words)
                        for gstin in found:
                            if is_valid_gstin_format(gstin):
                                g = gstin.upper()
                                all_gstins.add(g)
                                if has_company:
                                    contextual_gstins.add(g)
    except Exception:
        pass

    return {"all": list(all_gstins)[:15], "contextual": list(contextual_gstins)[:10]}


async def _google_gstin_site_search(company_name: str) -> dict:
    """Search Google on GST directory sites for company GSTINs.
    
    Returns a dict with:
      - 'all': all GSTINs found on the page
      - 'contextual': GSTINs found in text blocks that also mention the company name
    """
    if not SCRAPER_API_KEY:
        return {"all": [], "contextual": []}

    all_gstins = set()
    contextual_gstins = set()
    query = f'"{company_name}" GSTIN site:knowyourgst.com OR site:gstzen.in OR site:mastersindia.com OR site:cleartax.in'
    target = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10&hl=en&gl=in"
    company_words = [w.lower() for w in company_name.split() if len(w) > 2]

    try:
        async with scraper_semaphore:
            async with httpx.AsyncClient(timeout=SCRAPER_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(scraper_url(target, country="in"))
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for tag in soup.find_all(["div", "span", "p", "li", "td", "a", "h3"]):
                        block_text = tag.get_text(separator=" ", strip=True)
                        if len(block_text) < 15 or len(block_text) > 500:
                            continue
                        found = GSTIN_PATTERN.findall(block_text)
                        block_lower = block_text.lower()
                        has_company = any(w in block_lower for w in company_words)
                        for gstin in found:
                            if is_valid_gstin_format(gstin):
                                g = gstin.upper()
                                all_gstins.add(g)
                                if has_company:
                                    contextual_gstins.add(g)
    except Exception:
        pass

    return {"all": list(all_gstins)[:10], "contextual": list(contextual_gstins)[:10]}


async def _try_google_gstin_lookup(gstin: str) -> dict:
    """Look up a specific GSTIN via Google to find cached registration details."""
    if not SCRAPER_API_KEY:
        return {"valid": False}

    target = f"https://www.google.com/search?q=GSTIN+{gstin}&hl=en&gl=in"
    try:
        async with scraper_semaphore:
            async with httpx.AsyncClient(timeout=SCRAPER_TIMEOUT, follow_redirects=True) as client:
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
                    re.compile(r'Business\s*Name[,\s]*([A-Z][A-Z\s&.,]+)', re.IGNORECASE),
                    re.compile(r'GST\s*Number\s*for\s*([A-Z][A-Z\s&.,]+)\s*is', re.IGNORECASE),
                    re.compile(r'([A-Z][A-Z\s&.,]+)\s*\(' + gstin + r'\)', re.IGNORECASE),
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