import json, os, random, time
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

# --- VENUS v123 KV PERSISTENCE ---
try:
    from upstash_redis import Redis
    redis = Redis.from_env()
    def kv_get(key, default):
        try:
            v = redis.get(key)
            if v is None: return default
            return json.loads(v) if isinstance(v, str) else v
        except: return default
    def kv_set(key, val):
        try: redis.set(key, json.dumps(val))
        except Exception as e: print(f"KV SET ERROR {key}: {e}")
    USE_KV = True
except Exception as e:
    print(f"KV fallback memory: {e}")
    _MEM = {}
    def kv_get(k,d): return _MEM.get(k,d)
    def kv_set(k,v): _MEM[k]=v
    USE_KV = False

# --- CONFIG v122 BEST LOGICAL ---
COINS = {
    "ULTRA": ["BONKUSDT","PEPEUSDT","SHIBUSDT","FLOKIUSDT"],
    "PENNY": ["BOMEUSDT","MEMEUSDT","TURBOUSDT","NEIROUSDT","DOGEUSDT","WIFUSDT"],
    "MAJOR": ["AVAXUSDT","LINKUSDT"]
}
AGENTS = {
    "Bridgewater": {"w":1.60,"rule":"Vol spike penny pump Vol>2.5x"},
    "Citadel": {"w":1.60,"rule":"BB breakout BB<-1.2 LONG >1.2 SHORT"},
    "Two Sigma": {"w":1.60,"rule":"ML score combines all"},
    "Renaissance": {"w":1.50,"rule":"RSI ultra <35 LONG >65 SHORT"},
    "Berkshire": {"w":1.40,"rule":"EMA trend 9>21>50"},
    "Millennium": {"w":1.40,"rule":"Consensus 4+ votes score>4.5"},
    "Soros": {"w":1.40,"rule":"BTC regime risk on/off"}
}
TP_CONFIG = {
    "ULTRA": {"order":25,"tp":1.5,"win":0.32,"time":"1-3m"},
    "PENNY": {"order":30,"tp":1.2,"win":0.30,"time":"5-15m"},
    "MID": {"order":30,"tp":1.2,"win":0.30,"time":"8-15m"},
    "MAJOR": {"order":50,"tp":0.8,"win":0.30,"time":"15-25m"}
}

def get_state():
    return {
        "open": kv_get("venus_open", []),
        "history": kv_get("venus_history", []),
        "cap": kv_get("venus_cap", 0.0),
        "daily": kv_get("venus_daily", 0.0),
        "total": kv_get("venus_total", 0),
        "wins": kv_get("venus_wins", 0),
        "losses": kv_get("venus_losses", 0),
        "last_cron": kv_get("venus_last_cron", "never"),
        "agents": kv_get("venus_agents", {k: {"W":0,"L":0,"PnL":0.0,"w":v["w"]} for k,v in AGENTS.items()})
    }

def save_state(s):
    kv_set("venus_open", s["open"])
    kv_set("venus_history", s["history"])
    kv_set("venus_cap", s["cap"])
    kv_set("venus_daily", s["daily"])
    kv_set("venus_total", s["total"])
    kv_set("venus_wins", s["wins"])
    kv_set("venus_losses", s["losses"])
    kv_set("venus_last_cron", s["last_cron"])
    kv_set("venus_agents", s["agents"])

def scan_coin(symbol):
    # Simulate real scan - score 2.0 - 9.5 conf 30-95%
    tier = "ULTRA" if symbol in COINS["ULTRA"] else "PENNY" if symbol in COINS["PENNY"] else "MAJOR"
    # Make FLOKI/BONK pump sometimes for demo
    base_score = random.uniform(2.0, 5.5)
    if symbol in ["FLOKIUSDT","BONKUSDT","MEMEUSDT"]:
        base_score += random.uniform(2.0, 4.0)
    conf = min(95, base_score * 10 + random.uniform(5,15))
    score = round(base_score,2)
    return {"symbol":symbol,"tier":tier,"score":score,"conf":round(conf,1),"price":round(random.uniform(0.000003, 15),8)}

@app.route('/api/cron')
def cron():
    state = get_state()
    now = datetime.now().strftime("%H:%M:%S")
    logs = []
    logs.append(f"[{now}] Cron: /api/cron every 30s via cron-job.org - keeps Vercel alive")

    # 1. Check TP/SL for open trades (1-3m ULTRA logic)
    new_open = []
    for t in state["open"]:
        # 70% win rate simulation for ULTRA
        age_sec = time.time() - t.get("opened_at", time.time())
        tier = t["tier"]
        target_time = 90 if tier=="ULTRA" else 400 if tier=="PENNY" else 900
        if age_sec > target_time:
            win = random.random() < 0.65 # 65% WR = BEST
            pnl = TP_CONFIG[tier]["win"] if win else -0.18
            state["cap"] += pnl
            state["daily"] += pnl
            state["total"] += 1
            if win: state["wins"]+=1
            else: state["losses"]+=1
            # update agents
            for ag in t.get("agents",[]):
                if ag in state["agents"]:
                    if win: state["agents"][ag]["W"]+=1
                    else: state["agents"][ag]["L"]+=1
                    state["agents"][ag]["PnL"]+=pnl
            state["history"].insert(0, {**t,"closed_at":time.time(),"pnl":pnl,"win":win})
            logs.append(f"[{now}] CLOSE {t['symbol']} {tier} PnL ${pnl} {'WIN' if win else 'LOSS'}")
        else:
            new_open.append(t)
    state["open"] = new_open

    # 2. Scan 12 coins BEST
    scans = []
    for cat in COINS:
        for sym in COINS[cat]:
            scans.append(scan_coin(sym))

    # Sort by score
    scans_sorted = sorted(scans, key=lambda x: x["score"], reverse=True)

    # 3. Open new trades if score>4.0 conf>52% and <10 open
    opened = 0
    for s in scans_sorted:
        if len(state["open"]) >= 10: break
        if s["score"]>4.0 and s["conf"]>52:
            if not any(o["symbol"]==s["symbol"] for o in state["open"]):
                tier_cfg = TP_CONFIG[s["tier"]]
                trade = {
                    "symbol": s["symbol"],
                    "tier": s["tier"],
                    "price": s["price"],
                    "order": tier_cfg["order"],
                    "tp": tier_cfg["tp"],
                    "win": tier_cfg["win"],
                    "score": s["score"],
                    "conf": s["conf"],
                    "agents": random.sample(list(AGENTS.keys()), k=random.randint(3,5)),
                    "opened_at": time.time(),
                    "opened_str": now
                }
                state["open"].append(trade)
                opened+=1
                logs.append(f"[{now}] OPEN {s['symbol']} {s['tier']} Score {s['score']} Conf {s['conf']}% ${tier_cfg['order']} TP {tier_cfg['tp']}%=${tier_cfg['win']} win")

    state["last_cron"] = datetime.now().isoformat()
    state["log"] = logs[-20:] # keep last 20
    kv_set("venus_scans", scans_sorted)
    kv_set("venus_log", logs)
    save_state(state)

    return jsonify({
        "status":"ok",
        "kv": USE_KV,
        "open": len(state["open"]),
        "opened_now": opened,
        "cap": state["cap"],
        "scans": scans_sorted[:5],
        "log": logs
    })

@app.route('/api/state')
def state_api():
    s = get_state()
    s["scans"] = kv_get("venus_scans", [])
    s["log"] = kv_get("venus_log", [])
    return jsonify(s)

@app.route('/')
def index():
    return jsonify({"message":"VENUS v123 BEST - use /api/state and frontend at vercel.app","cron":"/api/cron","state":"/api/state"})

# For Vercel serverless
def handler(request):
    return app(request)
