from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import json
import os
import urllib.request
import urllib.error

app = FastAPI(title="IndiaPulse Live Market Website")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public NSE_EQ Security IDs for tracked market stocks & ETFs (no personal account data)
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
    with urllib.request.urlopen(req, timeout=15) as resp:
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
    if not cid or not tok:
        raise HTTPException(
            status_code=400,
            detail="Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in Render Environment Variables.",
        )
    try:
        sec_ids = [int(k) for k in MARKET_SECURITIES.keys()]
        res = post_dhan_ltp(cid, tok, sec_ids)
        nse_data = res.get("data", {}).get("NSE_EQ", {}) if isinstance(res, dict) else {}
        quotes = {}
        for sec_id, info in nse_data.items():
            ticker = MARKET_SECURITIES.get(str(sec_id))
            if ticker and isinstance(info, dict) and "last_price" in info:
                quotes[ticker] = info["last_price"]
        return {"client_id": cid, "quotes": quotes}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=exc.code, detail=detail or str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
