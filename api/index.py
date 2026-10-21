""" VENUS v1088 - HIGH-VELOCITY MOMENTUM SPOT ENGINE (MOBILE OPTIMIZED) """
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, math
import hmac, hashlib

app = Flask(__name__)

API_KEY = os.environ.get("BINANCE_API_KEY", "")
SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY", "")

def get_live_usdt_balance(default_fallback=34.62):
    if not API_KEY or not SECRET_KEY:
        return default_fallback
    try:
        query_string = f"timestamp={int(time.time()*1000)}"
        signature = hmac.new(SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        url = f"https://api.binance.com/api/v3/account?{query_string}&signature={signature}"
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": API_KEY, "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            for asset in data.get("balances", []):
                if asset.get("asset") == "USDT":
                    free_val = float(asset.get("free", 0))
                    if free_val > 0:
                        return free_val
    except Exception:
        pass
    return default_fallback

def execute_binance_spot_buy(symbol, quote_amount_usdt):
    if not API_KEY or not SECRET_KEY:
        return False, "Missing API Keys"
    try:
        price_url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        req_p = urllib.request.Request(price_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_p, timeout=3) as r:
            curr_price = float(json.loads(r.read().decode()).get("price", 0))
        if curr_price <= 0: return False, "Invalid price"
        
        raw_qty = quote_amount_usdt / curr_price
        quantity = round(raw_qty, 2)
        if quantity <= 0: return False, "Quantity too small"

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
        full_query = f"{query_string}&signature={signature}"
        
        url = f"https://api.binance.com/api/v3/order?{full_query}"
        req = urllib.request.Request(url, method="POST", headers={"X-MBX-APIKEY": API_KEY, "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return True, json.loads(r.read().decode())
    except Exception as e:
        return False, str(e)

def execute_binance_spot_sell(symbol, base_quantity):
    if not API_KEY or not SECRET_KEY:
        return False, "Missing API Keys"
    try:
        timestamp = int(time.time() * 1000)
        query_params = {
            "symbol": f"{symbol}USDT",
            "side": "SELL",
            "type": "MARKET",
            "quantity": round(base_quantity, 2),
            "timestamp": timestamp
        }
        query_string = urllib.parse.urlencode(query_params)
        signature = hmac.new(SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        full_query = f"{query_string}&signature={signature}"
        url = f"https://api.binance.com/api/v3/order?{full_query}"
        req = urllib.request.Request(url, method="POST", headers={"X-MBX-APIKEY": API_KEY, "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return True, json.loads(r.read().decode())
    except Exception as e:
        return False, str(e)

INITIAL_LIVE_CAP = get_live_usdt_balance(34.62)
MEM_STATE={"cap":INITIAL_LIVE_CAP,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"open":[],"closed":[],"peak":INITIAL_LIVE_CAP,"equity":[INITIAL_LIVE_CAP],"daily_target_reached":False}

def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""

KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL","KV_URL","REDIS_URL"]) or "").rstrip("/")
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN","KV_REST_API_READ_ONLY_TOKEN","KV_TOKEN"])
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V1083_STATE"

MAXP=3
POS_PCT=33.33  
TOTAL_FEE=0.17
TP_PCT=1.00       
SL_PCT=10.50      
DOLLAR_PROFIT_LOCK = 0.50  

def kv_get(k):
    global MEM_STATE
    if not KV_URL or not KV_TOKEN: return MEM_STATE
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) and d else None
            if res: return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except: pass
    return MEM_STATE

def kv_set(k,o):
    global MEM_STATE
    MEM_STATE=o
    if not KV_URL or not KV_TOKEN: return True
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return "OK" in r.read().decode()
    except: return True

def kv_del(k):
    global MEM_STATE
    current_live_cap = get_live_usdt_balance(34.62)
    MEM_STATE={"cap":current_live_cap,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"open":[],"closed":[],"peak":current_live_cap,"equity":[current_live_cap],"daily_target_reached":False}
    if not KV_URL or not KV_TOKEN: return True
    try:
        body=json.dumps([["SET",k,json.dumps(MEM_STATE)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=4) as r: return True
    except: return True

def fetch_moving_momentum_targets(exclude_syms=[]):
    candidates = []
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/ticker/24hr"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                for item in data:
                    sym=item.get("symbol","")
                    if sym.endswith("USDT") and not any(x in sym for x in ["UP","DOWN","BULL","BEAR","TEST"]):
                        base=sym[:-4]
                        if base in exclude_syms or base in ["PUMP", "DUMMY"]: continue
                        vol=float(item.get("quoteVolume",0))
                        change=float(item.get("priceChangePercent",0))
                        if vol > 2000000 and change > 1.0:
                            candidates.append((base, change, vol))
                candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
                return [c[0] for c in candidates[:10]]
        except: continue
    return []

def fetch_live_price_fast(base):
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/ticker/price?symbol={base}USDT"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data=json.loads(r.read().decode()); price=float(data.get("price",0))
                if price > 0: return price, "binance"
        except: continue
    return None, "fail"

def fetch_klines_momentum_check(base):
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/klines?symbol={base}USDT&interval=5m&limit=10"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                closes=[float(k[4]) for k in data if len(k)>4]
                if len(closes)>=5:
                    ma_short = sum(closes[-3:]) / 3
                    ma_mid = sum(closes[-8:]) / min(8, len(closes))
                    if ma_short > ma_mid:
                        return True
        except: continue
    return False

def load_state():
    s=kv_get(STATE_KEY)
    if not s or not isinstance(s, dict) or "cap" not in s: s=MEM_STATE
    live_wallet_cap = get_live_usdt_balance(34.62)
    if live_wallet_cap > 0 and len(s.get("open", [])) == 0:
        s["cap"] = live_wallet_cap
        s["peak"] = max(s.get("peak", live_wallet_cap), live_wallet_cap)
    s.setdefault("scan",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("peak",live_wallet_cap)
    return s

def recalc(state):
    all_closed=state.get("closed",[]); state["wins"]=sum(1 for c in all_closed if c.get("net",0)>0); state["loss"]=sum(1 for c in all_closed if c.get("net",0)<0); state["total"]=len(all_closed)
    state["daily"]=sum([c.get("net",0) for c in all_closed[-100:]]) if all_closed else 0.0
    return state

def fill_missing_slots(state):
    open_tr = state.get("open", [])
    if len(open_tr) >= MAXP: return state
    
    cap = 30.0
    open_syms = [t["symbol"] for t in open_tr]
    targets = fetch_moving_momentum_targets(exclude_syms=open_syms)
    added = False
    
    for base in targets:
        if len(open_tr) >= MAXP: break
        if base in open_syms: continue
        
        if not fetch_klines_momentum_check(base): continue
        
        price, src = fetch_live_price_fast(base)
        if not price or price <= 0: continue
        
        pos_size = cap * (POS_PCT / 100.0)
        success, order_res = execute_binance_spot_buy(base, pos_size)
        if not success: continue  
            
        qty_purchased = pos_size / price
        tr = {
            "symbol": base,
            "side": "LONG",
            "entry": price,
            "price": price,
            "pos": pos_size,
            "qty": qty_purchased,
            "ts": int(time.time()),
            "tp": TP_PCT,
            "sl": SL_PCT,
            "reason": f"MOMENTUM SPOT LONG {base}"
        }
        open_tr.append(tr)
        open_syms.append(base)
        added = True
        
    if added:
        state["open"] = open_tr
        state = recalc(state)
        kv_set(STATE_KEY, state)
    return state

def auto_close_trades(state):
    cap=state.get("cap",34.62); new_open=[]; closed_added=False
    for tr in state.get("open",[]):
        sym=tr["symbol"]; entry=tr["entry"]; pos=tr["pos"]; qty=tr.get("qty", pos/entry)
        live_price,_=fetch_live_price_fast(sym)
        if not live_price or live_price<=0: 
            new_open.append(tr)
            continue
        pct=(live_price-entry)/entry*100
        net_val = pos * (pct - TOTAL_FEE) / 100
        
        should_close=False; close_reason=""
        if net_val >= DOLLAR_PROFIT_LOCK:
            should_close=True; close_reason=f"PROFIT TARGET SECURED (+${net_val:.2f})"
        elif pct <= -SL_PCT: 
            should_close=True; close_reason=f"SL TRIGGERED"
        
        if should_close:
            execute_binance_spot_sell(sym, qty)
            cap += net_val
            state["closed"].insert(0, {"symbol": sym, "side": "LONG", "net": net_val, "reason": close_reason})
            closed_added=True
        else:
            tr["price"]=live_price
            new_open.append(tr)
            
    if closed_added:
        state["open"]=new_open; state["cap"]=cap
        state = recalc(state)
        kv_set(STATE_KEY, state)
    state = fill_missing_slots(state)
    return state

def render(state):
    state=auto_close_trades(state); state=fill_missing_slots(state); state=recalc(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",34.62); wins=state.get("wins",0); loss=state.get("loss",0)
    
    trade_boxes_html=""
    for tr in open_tr:
        sym=tr["symbol"]; pos=tr.get("pos",10.0); entry=tr.get("entry",0)
        trade_boxes_html+=f"<div style='border:2px solid #0f8;background:#151515;border-radius:12px;padding:12px;margin:10px 0;font-size:14px;'><b>🚀 ACTIVE TRADE: {sym} SPOT LONG</b><br>Size: ${pos:.2f} | Entry: ${entry:.2f}</div>"

    if not open_tr:
        trade_boxes_html="<div style='text-align:center;color:#0f8;padding:20px;border:2px solid #0f8;border-radius:12px;background:#111;font-size:15px;'><b>🔍 HIGH-VELOCITY SCANNER ACTIVE</b><br><span style='font-size:12px;color:#aaa;'>Scanning for active surging momentum coins...</span></div>"
        
    closed_html = "".join([f"<div style='background:#111;padding:8px;border-radius:8px;font-size:12px;margin-bottom:6px;'><b>{c.get('symbol')}</b>: <span style='color:#0f8;'>${c.get('net'):+.2f}</span></div>" for c in closed[:20]]) or "<div style='color:#666;text-align:center;font-size:13px;'>No trades yet.</div>"

    return f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>
    body{{background:#0a0a0a;color:#eee;font-family:monospace;padding:12px;font-size:14px;}}
    .btn{{background:#0f8;color:#000;padding:12px 18px;font-weight:900;border:0;border-radius:8px;font-size:14px;cursor:pointer;text-decoration:none;display:inline-block;margin:4px;}}
    .btn-reset{{background:#f44;color:#fff;}}
    </style></head><body>
    <h2 style='color:#0f8;font-size:18px;'>⚡ VENUS MOMENTUM ENGINE</h2>
    <div style='background:#151515;padding:12px;border-radius:8px;margin-bottom:12px;font-size:15px;'>
        <b>AUM:</b> ${cap:.2f} &nbsp;|&nbsp; <b>Wins:</b> {wins} &nbsp;|&nbsp; <b>Losses:</b> {loss}
    </div>
    <div style='margin-bottom:14px;'>
        <a class='btn' href='?key={ADMIN_KEY}'>SYNC STATE</a>
        <a class='btn btn-reset' href='/api/reset?key={ADMIN_KEY}'>WIPE DATA</a>
    </div>
    <hr style='border-color:#333;margin:14px 0;'>
    <h3 style='font-size:16px;'>Active Trades</h3>
    {trade_boxes_html}
    <h3 style='font-size:16px;margin-top:20px;'>Recent Ledger</h3>
    {closed_html}
    </body></html>"""

@app.route('/', defaults={'path': ''}, methods=['GET','POST'])
@app.route('/<path:path>', methods=['GET','POST'])
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY)
        return Response(json.dumps({"ok":True}), mimetype="application/json")
    try:
        st=load_state()
        return Response(render(st), mimetype="text/html")
    except Exception as e:
        return Response(f"Error {e}", status=200)
