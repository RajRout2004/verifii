import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from scraper import scrape_supplier
from gst import lookup_gstin, search_gstin_by_name
from ai import get_verdict
from database import init_db, save_result, get_history

app = FastAPI(title="Verifii API", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "https://verifii-two.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# Hard timeout for the entire verification pipeline (seconds)
VERIFY_TIMEOUT = 55


class VerifyRequest(BaseModel):
    query: str
    website: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    company_name: Optional[str] = None  # From GSTIN search: use for web scraping


class GSTINSearchRequest(BaseModel):
    company_name: str


async def _run_verification(query: str, website: str | None, email: str | None,
                            gstin_input: str | None, company_name: str | None):
    """Core verification logic.
    
    When verifying a GSTIN:
      - If company_name is provided (from GSTIN search click): run GST + web scraping PARALLEL
      - If no company_name (user typed GSTIN directly): resolve name from GST first, then scrape
    """
    gstin_to_check = gstin_input or query
    is_gstin = len(gstin_to_check) == 15 and gstin_to_check[:2].isdigit()

    if is_gstin:
        if company_name:
            # We already know the company name → run everything in PARALLEL (fast path)
            gst_task = asyncio.create_task(lookup_gstin(gstin_to_check))
            web_task = asyncio.create_task(scrape_supplier(company_name, website, email))

            gst_data, web_data = await asyncio.gather(gst_task, web_task, return_exceptions=True)

            if isinstance(gst_data, Exception):
                gst_data = {"valid": False, "error": str(gst_data)}
            if isinstance(web_data, Exception):
                web_data = {"error": str(web_data)}
        else:
            # No company name → resolve from GST lookup first, then scrape with the name
            gst_data = await lookup_gstin(gstin_to_check)
            if isinstance(gst_data, Exception):
                gst_data = {"valid": False, "error": str(gst_data)}

            # Extract company name for web search
            name_for_web = None
            if isinstance(gst_data, dict):
                for key in ("trade_name", "legal_name"):
                    val = gst_data.get(key, "")
                    if val and val not in ("N/A", "Could not fetch from registry", ""):
                        name_for_web = val
                        break

            web_data = await scrape_supplier(name_for_web or query, website, email)
            if isinstance(web_data, Exception):
                web_data = {"error": str(web_data)}
    else:
        # Company name search — run web scraping AND GSTIN discovery in PARALLEL
        gst_data = {}
        web_task = asyncio.create_task(scrape_supplier(query, website, email))
        gstin_task = asyncio.create_task(search_gstin_by_name(query))

        web_data, gstin_search_result = await asyncio.gather(web_task, gstin_task, return_exceptions=True)
        if isinstance(web_data, Exception):
            web_data = {"error": str(web_data)}
        if isinstance(gstin_search_result, Exception):
            gstin_search_result = {"total_found": 0, "gstins": []}

        # Store GSTIN discovery results as a summary for the frontend
        gst_data = {
            "gstin_count": gstin_search_result.get("total_found", 0),
            "gstins_found": gstin_search_result.get("gstins", []),
            "search_type": "company_name",
        }

    verdict = await get_verdict(query, gst_data, web_data)
    save_result(query, verdict)

    return {
        "query": query,
        "gst_data": gst_data,
        "web_data": web_data,
        "verdict": verdict,
    }


@app.post("/verify")
async def verify_supplier(req: VerifyRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        result = await asyncio.wait_for(
            _run_verification(query, req.website, req.email, req.gstin, req.company_name),
            timeout=VERIFY_TIMEOUT,
        )
        return result
    except asyncio.TimeoutError:
        # If the whole pipeline takes too long, return a partial result
        return {
            "query": query,
            "gst_data": {},
            "web_data": {},
            "verdict": {
                "trust_score": 50,
                "verdict": "YELLOW",
                "summary": f"Verification timed out after {VERIFY_TIMEOUT}s. Some external services may be slow or unavailable. Try again.",
                "reasons": [
                    "Backend timed out while collecting data from external sources",
                    "This usually happens when ScraperAPI or GST portal is slow",
                ],
                "red_flags": ["Incomplete data — could not finish all checks"],
                "positive_signals": [],
                "recommendation": "Try again in a minute. If it keeps timing out, enter a GSTIN directly for faster results.",
            },
        }


@app.post("/gstin-search")
async def gstin_search(req: GSTINSearchRequest):
    """Search all GSTINs for a company name across all Indian states."""
    if not req.company_name.strip():
        raise HTTPException(status_code=400, detail="Company name cannot be empty")
    try:
        result = await asyncio.wait_for(
            search_gstin_by_name(req.company_name.strip()),
            timeout=30,
        )
        return result
    except asyncio.TimeoutError:
        return {
            "company_name": req.company_name,
            "total_found": 0,
            "gstins": [],
            "note": "Search timed out. Try entering the GSTIN directly.",
        }


@app.get("/history")
def history():
    return get_history()


@app.get("/")
def root():
    return {"status": "Verifii backend running", "version": "3.1.0"}