import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from scraper import scrape_supplier
from gst import lookup_gstin
from ai import get_verdict
from database import init_db, save_result, get_history

app = FastAPI(title="Verifii API", version="2.0.0")

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


class VerifyRequest(BaseModel):
    query: str
    website: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None


@app.post("/verify")
async def verify_supplier(req: VerifyRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    gst_data = {}
    web_data = {}

    gstin_to_check = req.gstin or query
    is_gstin = len(gstin_to_check) == 15 and gstin_to_check[:2].isdigit()

    if is_gstin:
        gst_data = await lookup_gstin(gstin_to_check)
        name_for_web = gst_data.get("legal_name") or gst_data.get("trade_name")
        if name_for_web and name_for_web != "N/A" and name_for_web != "Could not fetch from registry":
            web_data = await scrape_supplier(name_for_web, req.website, req.email)
        else:
            web_data = await scrape_supplier(query, req.website, req.email)
    else:
        web_data = await scrape_supplier(query, req.website, req.email)

    verdict = await get_verdict(query, gst_data, web_data)
    save_result(query, verdict)

    return {
        "query": query,
        "gst_data": gst_data,
        "web_data": web_data,
        "verdict": verdict,
    }

@app.post("/debug")
async def debug(req: VerifyRequest):
    web_data = await scrape_supplier(req.query)
    return web_data

@app.get("/nettest")
async def nettest():
    import httpx
    results = {}
    urls = [
        ("google", "https://www.google.com"),
        ("scraperapi", "http://api.scraperapi.com?api_key=" + os.environ.get("SCRAPER_API_KEY", "") + "&url=https://www.indiamart.com"),
    ]
    async with httpx.AsyncClient(timeout=10) as client:
        for name, url in urls:
            try:
                resp = await client.get(url)
                results[name] = {"status": resp.status_code, "length": len(resp.text)}
            except Exception as e:
                results[name] = {"error": str(e)}
    return results    

@app.get("/history")
def history():
    return get_history()


@app.get("/")
def root():
    return {"status": "Verifii backend running", "version": "2.0.0"}