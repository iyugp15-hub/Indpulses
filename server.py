from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import csv
import io
import json
import os
import urllib.request
import urllib.parse

app = FastAPI(title="IndiaPulse Live Market Website")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CACHE = {
    "all_funds": None,
    "all_equities": None,
}

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

FLAGSHIP_MF_CODES = {
    "PPFAS_FC": 122639,
    "HDFC_MID": 118989,
    "ICICI_MAA": 120334,
    "HDFC_FC": 118955,
    "ICICI_BC": 120586,
    "NIPPON_SC": 118778,
    "SBI_CONTRA": 119835,
    "SBI_LC": 119598,
    "SBI_MAA": 119718,
    "NIPPON_MAA": 148381,
    "KOTAK_MAA": 152069,
    "QUANT_MAA": 120821,
}

def http_get_text(url: str, headers: dict | None = None, timeout: int = 8) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")

def http_get_json(url: str, headers: dict | None = None, timeout: int = 8):
    return json.loads(http_get_text(url, headers={"Accept": "application/json", **(headers or {})}, timeout=timeout))

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
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_yahoo_symbol(symbol: str):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1d&interval=1d"
        data = http_get_json(url, timeout=5)
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose") or price
        chg_pct = ((price - prev) / prev * 100) if (price and prev) else 0.0
        return symbol, {
            "price": round(float(price), 2) if price else None,
            "chgPct": round(float(chg_pct), 2),
        }
    except Exception:
        return symbol, None

def fetch_mf_nav(fund_id: str, code: int):
    try:
        latest = http_get_json(f"https://api.mfapi.in/mf/{code}/latest", timeout=5)
        nav_list = latest.get("data", []) if isinstance(latest, dict) else []
        if nav_list and nav_list[0].get("nav"):
            return fund_id, {"nav": round(float(nav_list[0]["nav"]), 2), "date": nav_list[0].get("date", "")}
    except Exception:
        pass
    return fund_id, None

@app.get("/")
def serve_home():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

@app.get("/api/all-funds")
def get_all_funds(q: str = Query(default=""), limit: int = Query(default=500, le=5000)):
    if _CACHE["all_funds"] is None:
        raw = http_get_json("https://api.mfapi.in/mf", timeout=20)
        cleaned = []
        seen = set()
        for item in raw if isinstance(raw, list) else []:
            name = (item.get("schemeName") or "").strip()
            code = item.get("schemeCode")
            if not name or not code:
                continue
            display = name.replace(" - Direct Plan", "").replace(" Direct Plan", "").replace(" Direct", "").replace("(Direct)", "").strip()
            if display in seen:
                continue
            seen.add(display)
            cat = "Flexi Cap"
            nl = display.lower()
            if "mid" in nl:
                cat = "Mid Cap"
            elif "small" in nl:
                cat = "Small Cap"
            elif "large" in nl or "bluechip" in nl:
                cat = "Large Cap"
            elif "multi asset" in nl or "hybrid" in nl or "balanced" in nl:
                cat = "Hybrid"
            elif "index" in nl or "nifty" in nl:
                cat = "Index"
            elif "liquid" in nl or "debt" in nl or "gilt" in nl or "bond" in nl:
                cat = "Debt"
            cleaned.append({"schemeCode": code, "name": display, "category": cat})
        _CACHE["all_funds"] = cleaned

    ql = q.strip().lower()
    items = _CACHE["all_funds"]
    if ql:
        items = [f for f in items if ql in f["name"].lower() or ql == str(f["schemeCode"])]
    return {"total": len(_CACHE["all_funds"]), "matched": len(items), "funds": items[:limit]}

@app.get("/api/fund/{scheme_code}")
def get_fund_detail(scheme_code: int):
    data = http_get_json(f"https://api.mfapi.in/mf/{scheme_code}", timeout=10)
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    nav_history = data.get("data", []) if isinstance(data, dict) else []
    latest_nav = float(nav_history[0]["nav"]) if nav_history else 0.0
    return {
        "schemeCode": scheme_code,
        "schemeName": (meta.get("scheme_name") or "").replace(" Direct", "").strip(),
        "amc": meta.get("fund_house", "AMFI Registered"),
        "category": meta.get("scheme_category", "Mutual Fund"),
        "nav": round(latest_nav, 2),
        "history": nav_history[:30],
    }

@app.get("/api/all-equities")
def get_all_equities(q: str = Query(default=""), limit: int = Query(default=500, le=5000)):
    if _CACHE["all_equities"] is None:
        csv_text = http_get_text("https://images.dhan.co/api-data/api-scrip-master.csv", timeout=25)
        reader = csv.DictReader(io.StringIO(csv_text))
        equities = []
        seen = set()
        for row in reader:
            exch = (row.get("SEM_EXM_EXCH_ID") or "").strip().upper()
            series = (row.get("SEM_SERIES") or "").strip().upper()
            sym = (row.get("SEM_TRADING_SYMBOL") or "").strip().upper()
            if exch == "NSE" and series in ("EQ", "BE") and sym and sym not in seen:
                seen.add(sym)
                equities.append({
                    "ticker": sym,
                    "company": (row.get("SEM_CUSTOM_SYMBOL") or sym).strip(),
                    "securityId": (row.get("SEM_SMST_SECURITY_ID") or "").strip(),
                    "isEtf": "BEES" in sym or "ETF" in sym or "IETF" in sym,
                })
        _CACHE["all_equities"] = equities

    ql = q.strip().lower()
    items = _CACHE["all_equities"]
    if ql:
        items = [e for e in items if ql in e["ticker"].lower() or ql in e["company"].lower()]
    return {"total": len(_CACHE["all_equities"]), "matched": len(items), "equities": items[:limit]}

@app.get("/api/stock/{ticker}")
def get_stock_az_detail(ticker: str):
    """Fetches A-to-Z live market details for any NSE stock or ETF."""
    sym = ticker.strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}.NS?range=5d&interval=1d"
    data = http_get_json(url, timeout=8)
    result = data.get("chart", {}).get("result", [{}])[0]
    meta = result.get("meta", {})
    price = float(meta.get("regularMarketPrice") or 0)
    prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or price or 1)
    chg_pct = ((price - prev) / prev * 100) if prev else 0.0
    return {
        "ticker": sym,
        "exchange": meta.get("fullExchangeName", "NSE"),
        "currency": meta.get("currency", "INR"),
        "ltp": round(price, 2),
        "prevClose": round(prev, 2),
        "dayChangePct": round(chg_pct, 2),
        "dayHigh": round(float(meta.get("regularMarketDayHigh") or 0), 2),
        "dayLow": round(float(meta.get("regularMarketDayLow") or 0), 2),
        "week52High": round(float(meta.get("fiftyTwoWeekHigh") or 0), 2),
        "week52Low": round(float(meta.get("fiftyTwoWeekLow") or 0), 2),
        "volume": int(meta.get("regularMarketVolume") or 0),
        "instrumentType": meta.get("instrumentType", "EQUITY"),
    }

@app.get("/api/iceberg/{ticker}")
def scan_iceberg_activity(ticker: str):
    """Scans live 1-minute intraday candles for institutional accumulation / split-order volume bursts."""
    sym = ticker.strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}.NS?range=1d&interval=1m"
    data = http_get_json(url, timeout=8)
    result = data.get("chart", {}).get("result", [{}])[0]
    meta = result.get("meta", {})
    timestamps = result.get("timestamp", []) or []
    quote = (result.get("indicators", {}).get("quote", [{}]) or [{}])[0]
    closes = quote.get("close", []) or []
    highs = quote.get("high", []) or []
    lows = quote.get("low", []) or []
    vols = quote.get("volume", []) or []

    valid_vols = [v for v in vols if isinstance(v, (int, float)) and v > 0]
    avg_vol = (sum(valid_vols) / len(valid_vols)) if valid_vols else 1

    clusters = []
    for i in range(max(0, len(timestamps) - 60), len(timestamps)):
        v = vols[i] if i < len(vols) else 0
        c = closes[i] if i < len(closes) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        if not v or c is None:
            continue
        ratio = v / avg_vol if avg_vol else 1.0
        spread_pct = ((h - l) / c * 100) if (h and l and c) else 0.0
        if ratio >= 2.0:
            clusters.append({
                "ts": timestamps[i],
                "price": round(float(c), 2),
                "volume": int(v),
                "volRatio": round(ratio, 2),
                "spreadPct": round(spread_pct, 2),
                "signal": "Tight-Spread Accumulation (Iceberg Signature)" if spread_pct <= 0.25 else "Institutional Block / Burst",
            })

    return {
        "ticker": sym,
        "ltp": round(float(meta.get("regularMarketPrice") or 0), 2),
        "avg1mVolume": int(avg_vol),
        "clusters": list(reversed(clusters))[:15],
    }

@app.get("/api/live-sync")
def live_sync(
    access_token: str | None = Header(default=None, alias="access-token"),
    client_id: str | None = Header(default=None, alias="client-id"),
):
    cid = (client_id or os.environ.get("DHAN_CLIENT_ID", "")).strip()
    tok = (access_token or os.environ.get("DHAN_ACCESS_TOKEN", "")).strip()

    quotes = {}
    changes = {}
    nifty = None
    dhan_error = None
    source = "Live NSE + MFapi"

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
        except Exception as exc:
            dhan_error = str(exc)

    missing_tickers = [t for t in MARKET_SECURITIES.values() if t not in quotes]
    fund_navs = {}

    with ThreadPoolExecutor(max_workers=14) as pool:
        nifty_fut = pool.submit(fetch_yahoo_symbol, "^NSEI")
        quote_futures = {pool.submit(fetch_yahoo_symbol, f"{t}.NS"): t for t in missing_tickers}
        mf_futures = [pool.submit(fetch_mf_nav, fid, code) for fid, code in FLAGSHIP_MF_CODES.items()]

        _, nifty_info = nifty_fut.result()
        if nifty_info and nifty_info.get("price"):
            nifty = nifty_info

        for fut in as_completed(quote_futures):
            t = quote_futures[fut]
            _, info = fut.result()
            if info and info.get("price"):
                quotes[t] = info["price"]
                changes[t] = info["chgPct"]

        for fut in as_completed(mf_futures):
            fid, info = fut.result()
            if info:
                fund_navs[fid] = info

    return {
        "source": source,
        "dhan_error": dhan_error,
        "nifty": nifty,
        "quotes": quotes,
        "changes": changes,
        "fundNavs": fund_navs,
    }
