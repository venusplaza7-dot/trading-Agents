from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse
import hmac, hashlib

app = Flask(__name__)

# Replace with your actual Binance keys
API_KEY = "YOUR_BINANCE_API_KEY"
SECRET_KEY = "YOUR_BINANCE_SECRET_KEY"

def get_live_usdt_balance(default_fallback=34.62):
    if not API_KEY or "YOUR_" in API_KEY or not SECRET_KEY: return default_fallback
    try:
        query_string = f"timestamp={int(time.time()*1000)}"
        signature = hmac.new(SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        url = f"https://api.binance.com/api/v3/account?{query_string}&signature={signature}"
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": API_KEY, "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            for asset in data.get("balances", []):
                if asset.get("asset") == "USDT":
                    val = float(asset.get("free", 0))
                    if val > 0: return val
    except Exception:
        pass
    return default_fallback

def execute_binance_spot_buy(symbol, quote_amount_usdt):
    if not API_KEY or "YOUR_" in API_KEY or not SECRET_KEY: return False, "Missing API Keys"
    try:
        price_url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        req_p = urllib.request.Request(price_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_p, timeout=3) as r:
            curr_price = float(json.loads(r.read().decode()).get("price", 0))
        if curr_price <= 0: return False, "Invalid price"
        
        safe_amount = max(quote_amount_usdt, 11.0)
        raw_qty = safe_amount / curr_price
        quantity = round(raw_qty, 1 if raw_qty < 10 else 0)
        if quantity <= 0: quantity = round(raw_qty, 3)

        timestamp = int(time.time() * 1000)
        query_params = {
            "symbol": f"{symbol}USDT",
            "side": "BUY",
            "type": "MARKET",
            "quantity": quantity,
            "timestamp": timestamp
        }
        query_string = urllib.parse.urlencode(query_params)
        signature = hmac.new(SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        url = f"https://api.binance.com/api/v3/order?{query_string}&signature={signature}"
        
        req = urllib.request.Request(url, method="POST", headers={"X-MBX-APIKEY": API_KEY, "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return True, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        return False, f"HTTP {e.code}: {err_msg}"
    except Exception as e:
        return False, str(e)

MEM_STATE = {"cap": 34.62, "open": [], "error": ""}
ADMIN_KEY = "venus727"

@app.route('/', defaults={'path': ''}, methods=['GET','POST'])
@app.route('/<path:path>', methods=['GET','POST'])
def catch_all(path):
    state = MEM_STATE
    if len(state["open"]) == 0:
        success, res = execute_binance_spot_buy("BTC", 11.0)
        if success:
            state["open"].append({"symbol": "BTC", "status": "FILLED"})
            state["error"] = ""
        else:
            state["error"] = str(res)
            
    err = state.get("error", "")
    err_box = f"<div style='background:#400;border:1px solid #f44;padding:10px;border-radius:8px;margin-bottom:10px;color:#ff8;'><b>Error:</b> {err}</div>" if err else ""
    
    return Response(f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>
    <body style='background:#0a0a0a;color:#eee;font-family:monospace;padding:15px;'>
    <h2 style='color:#0f8;'>⚡ VENUS V1088 LIVE ENGINE</h2>
    {err_box}
    <div style='background:#151515;padding:12px;border-radius:8px;margin-bottom:12px;'>
        <b>AUM:</b> ${state.get('cap', 34.62):.2f} &nbsp;|&nbsp; <b>Open Trades:</b> {len(state.get('open',[]))}
    </div>
    <a href='?key={ADMIN_KEY}'><button style='background:#0f8;padding:12px;font-weight:900;border-radius:6px;cursor:pointer;'>REFRESH & EXECUTE</button></a>
    </body></html>""", mimetype="text/html")
