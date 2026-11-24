from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import json
import os
import urllib.request
import urllib.parse
import urllib.error

app = FastAPI(title="IndiaPulse Live Market Website")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MARKET_SECURITIES = {
    "1333": "HDFCBANK",
    "4963": "ICICIBANK",
    "1660": "ITC",
    "2885": "RELIANCE",
    "11483": "LT",
    "3045": "SBIN",
    "10604": "BHARTIARTL",
    "5900": "AXISBANK",
    "1594": "INFY",
    "11536": "TCS",
    "19585": "BSE",
    "22377": "MAXHEALTH",
    "4204": "MOTHERSON",
    "3499": "TATASTEEL",
    "14977": "POWERGRID",
    "20374": "COALINDIA",
    "11630": "NTPC",
    "694": "CIPLA",
    "7229": "HCLTECH",
    "317": "BAJFINANCE",
    "1922": "KOTAKBANK",
    "5258": "INDUSINDBK",
    "2303": "HAL",
    "14299": "PFC",
    "15355": "RECLTD",
    "3063": "VEDL",
    "10576": "NIFTYBEES",
    "10578": "BANKBEES",
    "14428": "GOLDBEES",
    "10579": "JUNIORBEES",
    "2815": "LIQUIDBEES",
}

MF_SEARCH_QUERIES = {
    "PPFAS_FC": "Parag Parikh Flexi Cap Fund Direct Growth",
    "HDFC_MID": "HDFC Mid-Cap Opportunities Fund Direct Growth",
    "ICICI_MAA": "ICICI Prudential Multi-Asset Fund Direct Growth",
    "HDFC_FC": "HDFC Flexi Cap Fund Direct Growth",
    "ICICI_BC": "ICICI Prudential Bluechip Fund Direct Growth",
    "NIPPON_SC": "Nippon India Small Cap Fund Direct Growth",
    "SBI_CONTRA": "SBI Contra Fund Direct Growth",
    "SBI_LC": "SBI Bluechip Fund Direct Growth",
    "SBI_MAA": "SBI Multi Asset Allocation Fund Direct Growth",
    "NIPPON_MAA": "Nippon India Multi Asset Allocation Fund Direct Growth",
    "KOTAK_MAA": "Kotak Multi Asset Allocation Fund Direct Growth",
    "QUANT_MAA": "Quant Multi Asset Allocation Fund Direct Growth",
}

def http_get_json(url: str, headers: dict | None = None):
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))

def post_dhan_ltp(client_id: str, access_token: str, sec_ids: list[int]):
    body = json.dumps({"NSE_EQ": sec_ids}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.dhan.co/v2/marketfeed/ltp",
        data=body,
        method="POST",
        headers={
            "access-token": access_token,
            "client-id": client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "IndiaPulse/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

@app.get("/")
def serve_home():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

@app.get("/api/live-sync")
def live_sync(
    access_token: str | None = Header(default=None, alias="access-token"),
    client_id: str | None = Header(default=None, alias="client-id"),
):
    cid = (client_id or os.environ.get("DHAN_CLIENT_ID", "")).strip()
    tok = (access_token or os.environ.get("DHAN_ACCESS_TOKEN", "")).strip()

    quotes = {}
    source = "Yahoo NSE + MFapi"

    # 1. Try DhanHQ Market Quote LTP first if keys are configured in Render
    if cid and tok:
        try:
            sec_ids = [int(k) for k in MARKET_SECURITIES.keys()]
            res = post_dhan_ltp(cid, tok, sec_ids)
            nse_data = res.get("data", {}).get("NSE_EQ", {}) if isinstance(res, dict) else {}
            for sec_id, info in nse_data.items():
                ticker = MARKET_SECURITIES.get(str(sec_id))
                if ticker and isinstance(info, dict) and info.get("last_price"):
                    quotes[ticker] = info["last_price"]
            if quotes:
                source = "DhanHQ Live + MFapi"
        except Exception:
            pass

    # 2. Fallback to live NSE quotes via Yahoo Finance for any missing tickers
    for ticker in MARKET_SECURITIES.values():
        if ticker in quotes:
            continue
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}.NS?range=1d&interval=1d"
            data = http_get_json(url)
            meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            if price:
                quotes[ticker] = round(float(price), 2)
        except Exception:
            continue

    # 3. Fetch real live Mutual Fund NAVs from MFapi.in (free AMFI data)
    fund_navs = {}
    for fund_id, query in MF_SEARCH_QUERIES.items():
        try:
            search_res = http_get_json(
                f"https://api.mfapi.in/mf/search?q={urllib.parse.quote(query)}"
            )
            if isinstance(search_res, list) and search_res:
                code = search_res[0].get("schemeCode")
                if code:
                    latest = http_get_json(f"https://api.mfapi.in/mf/{code}/latest")
                    nav_list = latest.get("data", []) if isinstance(latest, dict) else []
                    if nav_list and nav_list[0].get("nav"):
                        fund_navs[fund_id] = {
                            "nav": round(float(nav_list[0]["nav"]), 2),
                            "date": nav_list[0].get("date", ""),
                        }
        except Exception:
            continue

    return {
        "source": source,
        "quotes": quotes,
        "fundNavs": fund_navs,
    }
