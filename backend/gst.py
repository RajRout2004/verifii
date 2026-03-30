import httpx
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

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


def get_state_from_gstin(gstin: str) -> str:
    code = gstin[:2] if len(gstin) >= 2 else ""
    return STATE_CODES.get(code, "Unknown State")


def is_valid_gstin_format(gstin: str) -> bool:
    pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
    return bool(re.match(pattern, gstin.upper()))


async def lookup_gstin(gstin: str) -> dict:
    """Look up a specific GSTIN."""
    gstin = gstin.strip().upper()

    result = await _try_gst_gov_api(gstin)
    if result.get("valid"):
        return result

    result = await _try_knowyourgst(gstin)
    if result.get("valid"):
        return result

    return _validate_format_only(gstin)


async def search_gstin_by_name(company_name: str) -> dict:
    """Search all GSTINs for a company name — returns list grouped by state."""
    results = []

    # Method 1: GST portal search by trade name
    try:
        url = f"https://services.gst.gov.in/services/api/search/taxpayerDetails?tradeName={company_name.replace(' ', '%20')}"
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
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

    # Method 2: Scrape knowyourgst search
    if not results:
        try:
            url = f"https://www.knowyourgst.com/gst-number-search/by-name/?name={company_name.replace(' ', '+')}"
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
                follow_redirects=True
            ) as client:
                resp = await client.get(url)
                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract GSTINs from page
                gstin_pattern = re.compile(r'\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b')
                page_text = soup.get_text()
                found_gstins = list(set(gstin_pattern.findall(page_text)))

                for gstin in found_gstins[:15]:
                    results.append({
                        "gstin": gstin,
                        "legal_name": company_name.upper(),
                        "trade_name": company_name.upper(),
                        "state": get_state_from_gstin(gstin),
                        "state_code": gstin[:2],
                        "status": "Found",
                        "registration_date": "N/A",
                        "business_type": "N/A",
                    })
        except Exception:
            pass

    # Sort by state code for clean display
    results.sort(key=lambda x: x.get("state_code", "99"))

    return {
        "company_name": company_name,
        "total_found": len(results),
        "gstins": results,
        "note": f"Found {len(results)} GSTIN registrations across India" if results else "No GSTINs found via API — try entering GSTIN directly",
    }


async def _try_gst_gov_api(gstin: str) -> dict:
    url = f"https://services.gst.gov.in/services/api/search/taxpayerDetails?gstin={gstin}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
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


async def _try_knowyourgst(gstin: str) -> dict:
    url = f"https://www.knowyourgst.com/gst-number-search/by-gstin/?gstin={gstin}"
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
            follow_redirects=True
        ) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            data = {}
            for row in soup.select("table tr, .result-row"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(strip=True)
                    if "legal" in label or "taxpayer name" in label:
                        data["legal_name"] = value
                    elif "trade" in label:
                        data["trade_name"] = value
                    elif "status" in label:
                        data["status"] = value
                    elif "registration" in label:
                        data["registration_date"] = value
                    elif "type" in label:
                        data["business_type"] = value

            if data.get("legal_name"):
                return {
                    "valid": True,
                    "gstin": gstin,
                    "legal_name": data.get("legal_name", "N/A"),
                    "trade_name": data.get("trade_name", "N/A"),
                    "status": data.get("status", "N/A"),
                    "state": get_state_from_gstin(gstin),
                    "state_code": gstin[:2],
                    "registration_date": data.get("registration_date", "N/A"),
                    "business_type": data.get("business_type", "N/A"),
                    "source": "KnowYourGST",
                }
    except Exception:
        pass
    return {"valid": False}


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