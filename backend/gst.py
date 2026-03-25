import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://services.gst.gov.in/services/searchtp",
}


async def lookup_gstin(gstin: str) -> dict:
    gstin = gstin.strip().upper()

    # Try Method 1: Official GST taxpayer search API
    result = await _try_gst_gov_api(gstin)
    if result.get("valid"):
        return result

    # Try Method 2: Scrape knowyourgst portal
    result = await _try_gst_portal_scrape(gstin)
    if result.get("valid"):
        return result

    # Try Method 3: GST portal direct
    result = await _try_gstno_api(gstin)
    return result


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
                        "state": data.get("pradr", {}).get("addr", {}).get("stcd", "N/A"),
                        "registration_date": data.get("rgdt", "N/A"),
                        "business_type": data.get("dty", "N/A"),
                        "source": "GST Gov API",
                    }
    except Exception:
        pass
    return {"valid": False}


async def _try_gst_portal_scrape(gstin: str) -> dict:
    url = f"https://www.knowyourgst.com/gst-number-search/by-gstin/?gstin={gstin}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            legal_name = ""
            trade_name = ""
            status = ""
            state = ""
            reg_date = ""
            biz_type = ""

            rows = soup.select("table tr, .gst-details tr, .result-table tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(strip=True)
                    if "legal" in label or "taxpayer name" in label:
                        legal_name = value
                    elif "trade" in label:
                        trade_name = value
                    elif "status" in label:
                        status = value
                    elif "state" in label:
                        state = value
                    elif "registration" in label or "effective" in label:
                        reg_date = value
                    elif "type" in label or "taxpayer type" in label:
                        biz_type = value

            if legal_name:
                return {
                    "valid": True,
                    "gstin": gstin,
                    "legal_name": legal_name,
                    "trade_name": trade_name or legal_name,
                    "status": status or "Active",
                    "state": state,
                    "registration_date": reg_date,
                    "business_type": biz_type,
                    "source": "KnowYourGST",
                }
    except Exception:
        pass
    return {"valid": False}


async def _try_gstno_api(gstin: str) -> dict:
    url = f"https://gst.gov.in/commonservice/taxpayerDetails?gstin={gstin}"
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    name = data.get("lgnm") or data.get("tradeName") or data.get("name")
                    if name:
                        return {
                            "valid": True,
                            "gstin": gstin,
                            "legal_name": name,
                            "trade_name": data.get("tradeName", name),
                            "status": data.get("status", "Active"),
                            "state": data.get("state", "N/A"),
                            "registration_date": data.get("regDate", "N/A"),
                            "business_type": data.get("taxpayerType", "N/A"),
                            "source": "GST Portal",
                        }
                except Exception:
                    pass
    except Exception:
        pass

    # Final fallback — validate GSTIN format and return partial info
    return _validate_format_only(gstin)


def _validate_format_only(gstin: str) -> dict:
    import re
    pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
    is_valid_format = bool(re.match(pattern, gstin))

    state_codes = {
        "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
        "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
        "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
        "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
        "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
        "16": "Tripura", "17": "Meghalaya", "18": "Assam",
        "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
        "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
        "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
        "32": "Kerala", "33": "Tamil Nadu", "36": "Telangana",
        "37": "Andhra Pradesh",
    }

    state_code = gstin[:2] if len(gstin) >= 2 else ""
    state = state_codes.get(state_code, "Unknown")
    pan = gstin[2:12] if len(gstin) >= 12 else ""

    return {
        "valid": is_valid_format,
        "gstin": gstin,
        "legal_name": "Could not fetch from registry",
        "trade_name": "N/A",
        "status": "Format valid — live data unavailable" if is_valid_format else "Invalid GSTIN format",
        "state": state,
        "registration_date": "N/A",
        "business_type": "N/A",
        "pan": pan,
        "source": "Format validation only",
        "note": "GST registry APIs are rate-limited. GSTIN format is valid." if is_valid_format else "Invalid GSTIN format.",
    }