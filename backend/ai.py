import os
import json
import re
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"), timeout=20.0)
MODEL = "llama-3.3-70b-versatile"


def build_prompt(query: str, gst_data: dict, web_data: dict) -> str:

    gst_section = ""
    if gst_data:
        if gst_data.get('search_type') == 'company_name':
            # Company name search — show GSTIN discovery results
            gstin_count = gst_data.get('gstin_count', 0)
            gstins = gst_data.get('gstins_found', [])
            gstin_list = "\n".join([
                f"  - {g.get('gstin', 'N/A')} | {g.get('state', 'N/A')} | Status: {g.get('status', 'N/A')}"
                for g in gstins[:8]
            ]) if gstins else "  None found"
            gst_section = f"""
=== GST REGISTRY (Company Name Search) ===
- Total GSTINs found: {gstin_count}
- GSTINs registered in India:
{gstin_list}
Note: {gstin_count} GSTIN registrations found across Indian states. This indicates {'an active, registered business presence' if gstin_count > 0 else 'no GST registration was found — this is a concern for any legitimate business'}.
"""
        else:
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

    reviews_section = ""
    if web_data.get("google_reviews"):
        r = web_data["google_reviews"]
        snippets = "\n".join(r.get("snippets", []))
        reviews_section = f"""
=== GOOGLE REVIEWS ===
Snippets: {snippets or 'None found'}
"""

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
TradeIndia:
  - Found: {tradeindia.get('found', False)}
  - Companies: {', '.join(tradeindia.get('companies_found', [])) or 'None'}
Justdial:
  - Found: {justdial.get('found', False)}
  - Businesses: {', '.join(justdial.get('businesses_found', [])) or 'None'}
  - Ratings: {', '.join(justdial.get('ratings', [])) or 'None'}
"""

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
"""
        else:
            mca_section = "\n=== MCA ===\n- Not found on MCA portal\n"

    linkedin_section = ""
    linkedin = web_data.get("linkedin", {})
    if linkedin:
        linkedin_section = f"""
=== LINKEDIN PRESENCE ===
- Profile found: {linkedin.get('profile_found', False)}
- Links: {', '.join(linkedin.get('links', [])) or 'None found'}
"""

    website_section = ""
    website = web_data.get("website", {})
    if website:
        website_section = f"""
=== WEBSITE ANALYSIS ===
- URL: {website.get('url', 'N/A')}
- Accessible: {website.get('accessible', False)}
- Domain Age (years): {website.get('domain_age_years', 'Unknown')}
- Has Contact Info: {website.get('has_contact_info', False)}
- Has Physical Address: {website.get('has_address', False)}
- Has About Page: {website.get('has_about_page', False)}
- Professional Domain: {website.get('has_professional_domain', False)}
- Red Flags: {'; '.join(website.get('flags', [])) or 'None'}
"""

    email_section = ""
    email_check = web_data.get("email_check", {})
    if email_check:
        email_section = f"""
=== EMAIL DOMAIN CHECK ===
- Email: {email_check.get('email', 'N/A')}
- Professional: {email_check.get('is_professional', False)}
- Flags: {'; '.join(email_check.get('flags', [])) or 'None'}
"""

    scam_section = ""
    scam = web_data.get("scam_check", {})
    if scam:
        scam_section = f"""
=== SCAM / BLACKLIST CHECK ===
- Risk Level: {scam.get('risk_level', 'UNKNOWN')}
- Fraud flags found: {scam.get('fraud_flags', 0)}
- Flagged snippets: {'; '.join(scam.get('flagged_snippets', [])) or 'None'}
"""

    prompt = f"""You are a supplier due diligence expert for small businesses in India.
Analyze ALL the data below about a supplier and give a comprehensive trust verdict.

SUPPLIER QUERY: {query}

{gst_section}
{reviews_section}
{fraud_section}
{marketplace_section}
{mca_section}
{linkedin_section}
{website_section}
{email_section}
{scam_section}

CRITICAL CONTEXT — READ THIS FIRST:
- You are assessing whether this company is a TRUSTWORTHY B2B SUPPLIER to buy from.
- Consumer complaints (delivery issues, refund problems, app bugs, expired products) are COMPLETELY NORMAL for large consumer-facing companies like JioMart, Amazon, Flipkart, Swiggy, BigBasket, Tata, Reliance, Hindustan Unilever, etc.
- Do NOT treat consumer complaints as B2B fraud signals. A company with millions of customers will naturally have complaints online.
- "Scam" mentions on Google for well-known brands are almost always frustrated customers, NOT evidence of supplier fraud.
- Well-known brands with marketplace presence, verified listings, or government registrations should score HIGH (70+).
- Only consider GENUINE B2B fraud: fake companies, absconded directors, shell companies, money lost to supplier, advance payment scams, police cases.

SCORING GUIDE (start from 50, adjust based on evidence):

PENALTIES (apply ONCE each, NOT per mention):
- GST invalid or inactive → -30 points
- Genuine B2B fraud evidence (fake company, absconded, police case) → -25 points max total
- No marketplace presence AND no web presence at all → -15 points
- No LinkedIn presence (for companies claiming to be large) → -5 points
- Domain created less than 1 year ago → -15 points
- Using Gmail/free email for B2B → -10 points
- MCA strike-off → -20 points
- Consumer complaints only (delivery/refund/quality) → -5 points max (this is NORMAL)

BONUSES:
- GST active + name matches → +30 points
- Found on IndiaMART/TradeIndia with verified badge → +15 points
- LinkedIn company page exists → +10 points
- Website professional with domain age 3+ years → +15 points
- MCA active with regular filings → +20 points
- Well-known established brand recognized across India → +20 points
- Multiple marketplace listings or verified sellers → +10 points

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
- GREEN (70-100): Known brand OR multiple strong signals, marketplace presence, verified listings
- YELLOW (40-69): Some signals but gaps, unknown company, verify before large orders
- RED (0-39): Genuine B2B fraud evidence, fake/shell company, absconded directors, police cases
- IMPORTANT: Large consumer brands should almost NEVER be RED. Consumer complaints alone do NOT justify RED.
- Be specific — mention actual data found, not generic statements
- Write as if explaining to a kirana store owner who has never used software
- Do NOT include anything outside the JSON object
"""
    return prompt


async def get_verdict(query: str, gst_data: dict, web_data: dict) -> dict:
    prompt = build_prompt(query, gst_data, web_data)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a supplier due diligence expert. Always respond with valid JSON only. No markdown, no explanation, just the JSON object."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        raw = response.choices[0].message.content.strip()

        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
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
            "reasons": ["Groq API error", "Check GROQ_API_KEY environment variable"],
            "red_flags": ["AI backend unreachable"],
            "positive_signals": [],
            "recommendation": "Check Groq API key in Render environment variables.",
        }