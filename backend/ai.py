import httpx
import json
import re

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral"


def build_prompt(query: str, gst_data: dict, web_data: dict) -> str:

    # ── GST Section ──────────────────────────────────────────────────────────
    gst_section = ""
    if gst_data:
        gst_section = f"""
=== GST & TAX REGISTRATION ===
- GSTIN Valid: {gst_data.get('valid')}
- Legal Name: {gst_data.get('legal_name', 'N/A')}
- Trade Name: {gst_data.get('trade_name', 'N/A')}
- Status: {gst_data.get('status', 'N/A')}
- State: {gst_data.get('state', 'N/A')}
- Registration Date: {gst_data.get('registration_date', 'N/A')}
- Business Type: {gst_data.get('business_type', 'N/A')}
- Source: {gst_data.get('source', 'N/A')}
Note: {gst_data.get('note', '')}
"""

    # ── Google Reviews ────────────────────────────────────────────────────────
    reviews_section = ""
    if web_data.get("google_reviews"):
        r = web_data["google_reviews"]
        snippets = "\n".join(r.get("snippets", []))
        reviews_section = f"""
=== GOOGLE REVIEWS ===
Snippets: {snippets or 'None found'}
"""

    # ── Fraud & Complaints ────────────────────────────────────────────────────
    fraud_section = ""
    if web_data.get("google_fraud") or web_data.get("google_complaints"):
        fraud = web_data.get("google_fraud", {})
        complaints = web_data.get("google_complaints", {})
        fraud_section = f"""
=== FRAUD & COMPLAINT SIGNALS ===
- Fraud mentions found: {fraud.get('fraud_mentions', 0)}
- Fraud snippets: {'; '.join(fraud.get('fraud_snippets', [])) or 'None'}
- Complaint count: {complaints.get('complaint_count', 0)}
- Complaint snippets: {'; '.join(complaints.get('complaint_snippets', [])) or 'None'}
"""

    # ── B2B Marketplaces ──────────────────────────────────────────────────────
    marketplace_section = ""
    indiamart = web_data.get("indiamart", {})
    tradeindia = web_data.get("tradeindia", {})
    justdial = web_data.get("justdial", {})
    if indiamart or tradeindia or justdial:
        marketplace_section = f"""
=== B2B MARKETPLACE PRESENCE ===
IndiaMART:
  - Found: {indiamart.get('found', False)}
  - Companies: {', '.join(indiamart.get('companies_found', [])) or 'None'}
  - Verified listings: {indiamart.get('verified_count', 0)}
  - Years listed: {', '.join(indiamart.get('years_listed', [])) or 'N/A'}
TradeIndia:
  - Found: {tradeindia.get('found', False)}
  - Companies: {', '.join(tradeindia.get('companies_found', [])) or 'None'}
  - Verified: {tradeindia.get('verified_count', 0)}
Justdial:
  - Found: {justdial.get('found', False)}
  - Businesses: {', '.join(justdial.get('businesses_found', [])) or 'None'}
  - Ratings: {', '.join(justdial.get('ratings', [])) or 'None'}
"""

    # ── MCA Portal ────────────────────────────────────────────────────────────
    mca_section = ""
    mca = web_data.get("mca", {})
    if mca:
        companies = mca.get("companies", [])
        if companies:
            c = companies[0]
            mca_section = f"""
=== MCA (MINISTRY OF CORPORATE AFFAIRS) ===
- Found on MCA: {mca.get('found', False)}
- Company Name: {c.get('name', 'N/A')}
- CIN: {c.get('cin', 'N/A')}
- Status: {c.get('status', 'N/A')}
- Incorporation Date: {c.get('incorporation_date', 'N/A')}
- Company Type: {c.get('type', 'N/A')}
- State: {c.get('state', 'N/A')}
"""
        else:
            mca_section = "\n=== MCA ===\n- Not found on MCA portal\n"

    # ── Zauba Corp ────────────────────────────────────────────────────────────
    zauba_section = ""
    zauba = web_data.get("zauba", {})
    if zauba and zauba.get("found"):
        companies = zauba.get("companies", [])
        zauba_section = f"""
=== ZAUBA CORP (COMPANY REGISTRY) ===
- Found: {zauba.get('found', False)}
- Companies: {json.dumps(companies[:2])}
"""

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    linkedin_section = ""
    linkedin = web_data.get("linkedin", {})
    if linkedin:
        linkedin_section = f"""
=== LINKEDIN PRESENCE ===
- Profile found: {linkedin.get('profile_found', False)}
- Links: {', '.join(linkedin.get('links', [])) or 'None found'}
"""

    # ── Website Analysis ──────────────────────────────────────────────────────
    website_section = ""
    website = web_data.get("website", {})
    if website:
        website_section = f"""
=== WEBSITE ANALYSIS ===
- URL: {website.get('url', 'N/A')}
- Accessible: {website.get('accessible', False)}
- Domain: {website.get('domain', 'N/A')}
- Domain Age (years): {website.get('domain_age_years', 'Unknown')}
- Domain Created: {website.get('domain_creation_date', 'Unknown')}
- Has Contact Info: {website.get('has_contact_info', False)}
- Has Physical Address: {website.get('has_address', False)}
- Has About Page: {website.get('has_about_page', False)}
- Has Product Catalog: {website.get('has_product_catalog', False)}
- Professional Domain: {website.get('has_professional_domain', False)}
- Red Flags: {'; '.join(website.get('flags', [])) or 'None'}
"""

    # ── Email Check ───────────────────────────────────────────────────────────
    email_section = ""
    email_check = web_data.get("email_check", {})
    if email_check:
        email_section = f"""
=== EMAIL DOMAIN CHECK ===
- Email: {email_check.get('email', 'N/A')}
- Professional: {email_check.get('is_professional', False)}
- Flags: {'; '.join(email_check.get('flags', [])) or 'None'}
"""

    # ── Scam Databases ────────────────────────────────────────────────────────
    scam_section = ""
    scam = web_data.get("scam_check", {})
    if scam:
        scam_section = f"""
=== SCAM / BLACKLIST CHECK ===
- Risk Level: {scam.get('risk_level', 'UNKNOWN')}
- Fraud flags found: {scam.get('fraud_flags', 0)}
- Flagged snippets: {'; '.join(scam.get('flagged_snippets', [])) or 'None'}
"""

    # ── Build full prompt ─────────────────────────────────────────────────────
    prompt = f"""You are a supplier due diligence expert for small businesses in India.
Analyze ALL the data below about a supplier and give a comprehensive trust verdict.

SUPPLIER QUERY: {query}

{gst_section}
{reviews_section}
{fraud_section}
{marketplace_section}
{mca_section}
{zauba_section}
{linkedin_section}
{website_section}
{email_section}
{scam_section}

SCORING GUIDE:
- GST invalid or inactive → subtract 30 points immediately
- Fraud/scam mentions → subtract 20 points per credible mention
- No marketplace presence at all → subtract 10 points
- No LinkedIn presence (for a company claiming to be large) → subtract 5 points
- Domain created less than 1 year ago → subtract 15 points
- Using Gmail/free email for B2B → subtract 10 points
- MCA strike-off or not found (for Pvt Ltd/LLP) → subtract 20 points
- Multiple complaint snippets → subtract 10-20 points

BONUS POINTS:
- GST active + name matches → add 30 points
- Found on IndiaMART/TradeIndia with verified badge → add 15 points
- LinkedIn company page exists → add 10 points
- Website professional with domain age 3+ years → add 15 points
- MCA active with regular filings → add 20 points

Respond ONLY with a valid JSON object in this exact format, nothing else:
{{
  "trust_score": <number 0-100>,
  "verdict": "<RED | YELLOW | GREEN>",
  "summary": "<2-3 sentence plain English summary for a non-technical shop owner>",
  "reasons": [
    "<specific reason 1 with data reference>",
    "<specific reason 2 with data reference>",
    "<specific reason 3 with data reference>",
    "<specific reason 4 with data reference>"
  ],
  "red_flags": ["<red flag 1>", "<red flag 2>"],
  "positive_signals": ["<positive 1>", "<positive 2>"],
  "recommendation": "<clear action the business owner should take next>"
}}

Rules:
- GREEN (70-100): Multiple strong signals, GST active, marketplace presence, no complaints
- YELLOW (40-69): Some signals but gaps, verify before large orders
- RED (0-39): Serious red flags, missing key registrations, fraud signals found
- Be specific — mention actual data found, not generic statements
- Write as if explaining to a kirana store owner who has never used software
- Do NOT include anything outside the JSON object
"""
    return prompt


async def get_verdict(query: str, gst_data: dict, web_data: dict) -> dict:
    prompt = build_prompt(query, gst_data, web_data)

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(OLLAMA_URL, json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
            })

            data = resp.json()
            raw = data.get("response", "")

            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                # Ensure new fields exist even if model skips them
                parsed.setdefault("red_flags", [])
                parsed.setdefault("positive_signals", [])
                return parsed
            else:
                return {
                    "trust_score": 50,
                    "verdict": "YELLOW",
                    "summary": "Could not fully analyze this supplier. Try again.",
                    "reasons": ["AI response was unclear", "Re-run the search"],
                    "red_flags": [],
                    "positive_signals": [],
                    "recommendation": "Search manually before proceeding.",
                }

    except Exception as e:
        return {
            "trust_score": 0,
            "verdict": "RED",
            "summary": f"AI analysis failed: {str(e)}",
            "reasons": ["Ollama may not be running", "Check if mistral model is pulled"],
            "red_flags": ["AI backend unreachable"],
            "positive_signals": [],
            "recommendation": "Run: ollama serve, then restart backend.",
        }