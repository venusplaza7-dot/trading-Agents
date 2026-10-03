import json, os
try:
    from upstash_redis import Redis
    redis = Redis.from_env()  # reads KV_REST_API_URL + TOKEN you just connected
    USE_KV = True
except:
    redis = None
    USE_KV = False

def get_trades():
    if USE_KV:
        try:
            data = redis.get("venus_trades")
            return json.loads(data) if data else []
        except:
            return []
    return []

def save_trades(trades):
    if USE_KV:
        try:
            redis.set("venus_trades", json.dumps(trades))
        except Exception as e:
            print(f"KV save error: {e}")

def get_cap():
    if USE_KV:
        try:
            v = redis.get("venus_cap")
            return float(v) if v else 0.0
        except:
            return 0.0
    return 0.0

def save_cap(cap):
    if USE_KV:
        redis.set("venus_cap", str(cap))
import os, json, time, math, threading
from datetime import datetime
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

# BEST LOGICAL: 12 penny coins only - max frequency for $300 cap
PENNY_BEST = [
    ("BONKUSDT", "ultra", 25, 0.015, 0.0075),   # <$0.00001 - TP 1.5% = $0.32 win in 1-3m
    ("PEPEUSDT", "ultra", 25, 0.015, 0.0075),
    ("SHIBUSDT", "ultra", 25, 0.015, 0.0075),
    ("FLOKIUSDT", "ultra", 25, 0.015, 0.0075),
    ("BOMEUSDT", "penny", 30, 0.012, 0.006),    # $0.0005-$0.002 - TP 1.2% = $0.30 in 5-10m
    ("MEMEUSDT", "penny", 30, 0.012, 0.006),
    ("TURBOUSDT", "penny", 30, 0.012, 0.006),
    ("DOGEUSDT", "mid", 30, 0.012, 0.006),      # $0.08-$0.25 - TP 1.2% = $0.30 in 8-15m
    ("WIFUSDT", "mid", 30, 0.012, 0.006),
    ("NEIROUSDT", "penny", 30, 0.012, 0.006),
    ("AVAXUSDT", "major", 50, 0.008, 0.004),   # $10-$20 - TP 0.8% with $50 = $0.30 in 15-25m
    ("LINKUSDT", "major", 50, 0.008, 0.004),
]
SYMBOLS = [s[0] for s in PENNY_BEST]
TIER_MAP = {s[0]: {"tier": s[1], "order": s[2], "tp": s[3], "sl": s[4]} for s in PENNY_BEST}

MAX_CAP = 300.0
DAILY_GOAL = 50.0
FEE_PCT = 0.001

AGENTS = {
    "renaissance": {"name": "Renaissance", "weight": 1.5, "wins": 0, "losses": 0, "profit": 0.0, "desc": "RSI ultra <35 LONG >65 SHORT - mean reversion", "wr": 0},
    "citadel": {"name": "Citadel", "weight": 1.6, "wins": 0, "losses": 0, "profit": 0.0, "desc": "BB breakout BB<-1.2 LONG >1.2 SHORT - volatility", "wr": 0},
    "bridgewater": {"name": "Bridgewater", "weight": 1.6, "wins": 0, "losses": 0, "profit": 0.0, "desc": "Vol spike penny pump Vol>2.5x", "wr": 0},
    "berkshire": {"name": "Berkshire", "weight": 1.4, "wins": 0, "losses": 0, "profit": 0.0, "desc": "EMA trend 9>21>50", "wr": 0},
    "soros": {"name": "Soros", "weight": 1.4, "wins": 0, "losses": 0, "profit": 0.0, "desc": "BTC regime risk on/off", "wr": 0},
    "millennium": {"name": "Millennium", "weight": 1.4, "wins": 0, "losses": 0, "profit": 0.0, "desc": "Consensus 4+ votes score>4.5", "wr": 0},
    "twosigma": {"name": "Two Sigma", "weight": 1.6, "wins": 0, "losses": 0, "profit": 0.0, "desc": "ML score combines all", "wr": 0},
}

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
DATA_URL = "https://data-api.binance.vision"

training = {
    "total_trades": 0, "total_wins": 0, "total_losses": 0,
    "total_volume": 0.0, "total_fees": 0.0, "total_net": 0.0,
    "daily_pnl": 0.0, "real_cap_used": 0.0, "daily_goal": DAILY_GOAL,
    "agents": AGENTS, "history": [], "open_trades": [],
    "win_rate": 0.0, "auto_enabled": True, "v122": True,
    "mode": "v122 BEST LOGICAL 12 penny tiered $0.30 x 167 = $50/day max frequency",
    "trades_per_hour": 0, "best_penny": None, "cap": MAX_CAP,
    "last_cron": None, "cron_count": 0
}

def fetch_klines(symbol, interval="1m", limit=120):
    for base in [DATA_URL, "https://api.binance.com"]:
        try:
            r = requests.get(f"{base}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}", timeout=8)
            r.raise_for_status()
            data = r.json()
            if data and len(data)>0:
                return data
        except:
            continue
    return []

def fetch_after(symbol, after_ms, limit=500):
    for base in [DATA_URL, "https://api.binance.com"]:
        try:
            r = requests.get(f"{base}/api/v3/klines?symbol={symbol}&interval=1m&startTime={after_ms}&limit={limit}", timeout=8)
            r.raise_for_status()
            return r.json()
        except:
            continue
    return []

def calc_rsi(closes, p=14):
    if len(closes)<p+1: return 50
    g=l=0
    for i in range(len(closes)-p, len(closes)):
        d=closes[i]-closes[i-1]
        if d>0: g+=d
        else: l-=d
    g/=p; l/=p
    if l==0: return 100
    return 100-100/(1+g/l)

def calc_ema(arr, p):
    k=2/(p+1); e=arr[0]
    for v in arr[1:]: e=v*k+e*(1-k)
    return e

def calc_bb(closes, p=20, m=2):
    if len(closes)<p: return 0,0,0,0,0
    sl=closes[-p:]; mid=sum(sl)/p
    var=sum((x-mid)**2 for x in sl)/p; std=var**0.5
    up=mid+m*std; lo=mid-m*std
    bp=(closes[-1]-mid)/std if std!=0 else 0
    return mid, up, lo, bp, (up-lo)/mid*100 if mid!=0 else 0

def calc_vol(closes):
    if len(closes)<20: return 0.5
    rets=[math.log(closes[i]/closes[i-1]) if closes[i-1]!=0 else 0 for i in range(1,len(closes))]
    sl=rets[-20:]; mean=sum(sl)/len(sl) if sl else 0
    var=sum((x-mean)**2 for x in sl)/len(sl) if sl else 0
    return (var**0.5)*100*5

def scan_best(symbol, btc_up=True):
    try:
        tier_info = TIER_MAP.get(symbol, {"tier": "penny", "order": 30, "tp": 0.012, "sl": 0.006})
        klines=fetch_klines(symbol,"1m",120)
        if not klines:
            return {"symbol": symbol, "side": "WAIT", "score": 0, "price": 0, "voters": [], "confidence": 0, "order_size": tier_info["order"], "rsi": 50, "bb_pos": 0, "vol": 0, "tier": tier_info["tier"], "tp": tier_info["tp"], "sl": tier_info["sl"], "net_win": 0}
        closes=[float(k[4]) for k in klines]
        price=closes[-1]
        if price==0:
            return {"symbol": symbol, "side": "WAIT", "score": 0, "price": 0, "voters": [], "confidence": 0, "order_size": tier_info["order"], "rsi": 50, "bb_pos": 0, "vol": 0, "tier": tier_info["tier"], "tp": tier_info["tp"], "sl": tier_info["sl"], "net_win": 0}
        rsi=calc_rsi(closes)
        ema9=calc_ema(closes,9); ema21=calc_ema(closes,21); ema50=calc_ema(closes,50)
        mid, up, lo, bb_pos, bb_w = calc_bb(closes)
        vol=calc_vol(closes)
        votes_long=0; votes_short=0; score=0; voters=[]
        tier = tier_info["tier"]
        # Ultra penny needs stronger RSI for mean reversion
        if tier=="ultra":
            if rsi<28: votes_long+=AGENTS["renaissance"]["weight"]*1.6; score+=2.0*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi>72: votes_short+=AGENTS["renaissance"]["weight"]*1.6; score+=2.0*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi<35: votes_long+=AGENTS["renaissance"]["weight"]*1.2; score+=1.3*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi>65: votes_short+=AGENTS["renaissance"]["weight"]*1.2; score+=1.3*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
        else:
            if rsi<32: votes_long+=AGENTS["renaissance"]["weight"]*1.4; score+=1.6*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi>68: votes_short+=AGENTS["renaissance"]["weight"]*1.4; score+=1.6*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi<38: votes_long+=AGENTS["renaissance"]["weight"]; score+=1.1*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi>62: votes_short+=AGENTS["renaissance"]["weight"]; score+=1.1*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
        if bb_pos<-1.3: votes_long+=AGENTS["citadel"]["weight"]*1.4; score+=1.6*AGENTS["citadel"]["weight"]; voters.append("citadel")
        elif bb_pos>1.3: votes_short+=AGENTS["citadel"]["weight"]*1.4; score+=1.6*AGENTS["citadel"]["weight"]; voters.append("citadel")
        elif abs(bb_pos)>0.85:
            if bb_pos<0: votes_long+=AGENTS["citadel"]["weight"]
            else: votes_short+=AGENTS["citadel"]["weight"]
            score+=1.1*AGENTS["citadel"]["weight"]; voters.append("citadel")
        if vol>2.8: votes_long+=AGENTS["bridgewater"]["weight"]; votes_short+=AGENTS["bridgewater"]["weight"]; score+=1.4*AGENTS["bridgewater"]["weight"]; voters.append("bridgewater")
        elif vol>1.9: score+=0.8*AGENTS["bridgewater"]["weight"]; voters.append("bridgewater")
        if ema9>ema21 and ema21>ema50: votes_long+=AGENTS["berkshire"]["weight"]; score+=1.1*AGENTS["berkshire"]["weight"]; voters.append("berkshire")
        elif ema9<ema21 and ema21<ema50: votes_short+=AGENTS["berkshire"]["weight"]; score+=1.1*AGENTS["berkshire"]["weight"]; voters.append("berkshire")
        if btc_up: votes_long+=AGENTS["soros"]["weight"]*0.5; score+=0.5*AGENTS["soros"]["weight"]; voters.append("soros")
        else: votes_short+=AGENTS["soros"]["weight"]*0.5; score+=0.5*AGENTS["soros"]["weight"]; voters.append("soros")
        if votes_long+votes_short>=4 and score>4.8: score+=0.9*AGENTS["millennium"]["weight"]; voters.append("millennium")
        voters.append("twosigma")
        side = "LONG" if votes_long>votes_short and score>=4.0 else ("SHORT" if votes_short>votes_long and score>=4.0 else "WAIT")
        conf = min(95, (score/7.2)*100)
        order_size = tier_info["order"]
        tp_pct = tier_info["tp"]
        sl_pct = tier_info["sl"]
        fee = order_size*FEE_PCT*2
        net_win = order_size*tp_pct - fee
        net_loss = order_size*sl_pct + fee
        # Boost order for high score
        if score>6.5:
            order_size = min(60, order_size+10)
            net_win = order_size*tp_pct - order_size*FEE_PCT*2
        return {"symbol": symbol, "price": price, "rsi": round(rsi,1), "bb_pos": round(bb_pos,2), "vol": round(vol,2), "votes_long": round(votes_long,2), "votes_short": round(votes_short,2), "score": round(score,2), "side": side, "voters": voters, "confidence": round(conf,1), "order_size": order_size, "tier": tier, "tp": tp_pct, "sl": sl_pct, "net_win": round(net_win,2), "net_loss": round(net_loss,2), "reason": f"{tier} RSI {rsi:.1f} BB {bb_pos:.2f} Vol {vol:.1f}x Score {score:.1f}"}
    except Exception as e:
        tier_info = TIER_MAP.get(symbol, {"tier": "penny", "order": 30, "tp": 0.012, "sl": 0.006})
        return {"symbol": symbol, "side": "WAIT", "score": 0, "price": 0, "voters": [], "confidence": 0, "order_size": tier_info["order"], "rsi": 50, "bb_pos": 0, "vol": 0, "tier": tier_info["tier"], "tp": tier_info["tp"], "sl": tier_info["sl"], "net_win": 0, "error": str(e)}

def check_outcome(trade):
    try:
        symbol=trade["symbol"]; entry=trade["entry_price"]; side=trade["side"]; after=trade["entry_time_ms"]; qty=trade["quote_qty"]
        tp_pct=trade.get("tp_pct", 0.012); sl_pct=trade.get("sl_pct", 0.006)
        klines=fetch_after(symbol, after, 600)
        if not klines: return None
        tp = entry*(1+tp_pct) if side=="LONG" else entry*(1-tp_pct)
        sl = entry*(1-sl_pct) if side=="LONG" else entry*(1+sl_pct)
        fee = qty*FEE_PCT*2
        gross_win = qty*tp_pct
        net_win = gross_win - fee
        loss_net = qty*sl_pct + fee
        for k in klines:
            high=float(k[2]); low=float(k[3]); ot=k[0]
            if side=="LONG":
                if high>=tp: return {"result": "WIN", "exit": tp, "ot": ot, "bars": (ot-after)//60000, "gross": gross_win, "net": net_win, "fee": fee, "reason": f"TP +{tp_pct*100:.1f}% = ${net_win:.2f}"}
                if low<=sl: return {"result": "LOSS", "exit": sl, "ot": ot, "bars": (ot-after)//60000, "gross": -qty*sl_pct, "net": -loss_net, "fee": fee, "reason": f"SL -{sl_pct*100:.1f}% = -${loss_net:.2f}"}
            else:
                if low<=tp: return {"result": "WIN", "exit": tp, "ot": ot, "bars": (ot-after)//60000, "gross": gross_win, "net": net_win, "fee": fee, "reason": f"TP -{tp_pct*100:.1f}% = ${net_win:.2f}"}
                if high>=sl: return {"result": "LOSS", "exit": sl, "ot": ot, "bars": (ot-after)//60000, "gross": -qty*sl_pct, "net": -loss_net, "fee": fee, "reason": f"SL +{sl_pct*100:.1f}% = -${loss_net:.2f}"}
        return None
    except Exception as e:
        return None

def do_one_iteration():
    # Check open trades
    for trade in training["open_trades"][:]:
        out=check_outcome(trade)
        if out and out["result"] in ["WIN","LOSS"]:
            is_win = out["result"]=="WIN"
            training["total_trades"]+=1
            training["total_volume"]+=trade["quote_qty"]
            training["total_fees"]+=out["fee"]
            training["total_net"]+=out["net"]
            training["daily_pnl"]+=out["net"]
            if is_win:
                training["total_wins"]+=1
                for v in trade["voters"]:
                    if v in AGENTS:
                        AGENTS[v]["wins"]+=1
                        AGENTS[v]["profit"]+=out["net"]/len(trade["voters"])
                        AGENTS[v]["weight"]=min(2.0, AGENTS[v]["weight"]+0.04)
            else:
                training["total_losses"]+=1
                for v in trade["voters"]:
                    if v in AGENTS:
                        AGENTS[v]["losses"]+=1
                        AGENTS[v]["profit"]+=out["net"]/len(trade["voters"])
                        AGENTS[v]["weight"]=max(0.5, AGENTS[v]["weight"]-0.025)
            for aid in AGENTS:
                a=AGENTS[aid]; tot=a["wins"]+a["losses"]; a["wr"]=(a["wins"]/tot*100) if tot>0 else 0
            training["win_rate"]=(training["total_wins"]/max(1,training["total_trades"])*100)
            training["real_cap_used"]=max(0, training["real_cap_used"]-trade["quote_qty"])
            training["history"].append({"time": datetime.now().isoformat(), "symbol": trade["symbol"], "side": trade["side"], "is_win": is_win, "entry": trade["entry_price"], "exit": out["exit"], "pnl_net": out["net"], "qty": trade["quote_qty"], "voters": trade["voters"], "reason": out["reason"], "bars": out["bars"], "daily": training["daily_pnl"], "tier": trade.get("tier","penny")})
            if len(training["history"])>500: training["history"]=training["history"][-500:]
            training["open_trades"].remove(trade)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] v122 BEST {trade['symbol']} {trade['side']} {out['result']} ${out['net']:.2f} Daily ${training['daily_pnl']:.2f} WR {training['win_rate']:.1f}%", flush=True)

    if training["auto_enabled"] and training["daily_pnl"] < DAILY_GOAL and len(training["open_trades"]) < 10 and training["real_cap_used"] < MAX_CAP*0.97:
        try:
            btc1m=fetch_klines("BTCUSDT","1m",26)
            c=[float(k[4]) for k in btc1m] if btc1m else [0]
            btc_up = c[-1]>calc_ema(c,21) if len(c)>=21 else True
        except:
            btc_up=True
        results=[]
        for sym in SYMBOLS:
            if any(t["symbol"]==sym for t in training["open_trades"]):
                continue
            results.append(scan_best(sym, btc_up))
        signals=[r for r in results if r["side"]!="WAIT" and r["score"]>=4.0 and r["confidence"]>=52]
        # Sort by tier priority: ultra first (fastest TP), then penny, then major, and score
        def sort_key(x):
            tier_priority = {"ultra": 3, "penny": 2, "mid": 1.5, "major": 1}[x["tier"]]
            return tier_priority * x["score"] * x["confidence"]
        signals.sort(key=sort_key, reverse=True)
        if signals:
            best=signals[0]
            qty=best["order_size"]
            if training["real_cap_used"]+qty>MAX_CAP:
                qty=MAX_CAP-training["real_cap_used"]
            if qty>=20:
                kl=fetch_klines(best["symbol"],"1m",1)
                entry=float(kl[-1][4]) if kl else best["price"]
                if entry==0:
                    entry=best["price"]
                trade={"symbol": best["symbol"], "side": best["side"], "entry_price": entry, "entry_time_ms": int(time.time()*1000), "quote_qty": qty, "voters": best["voters"], "tp": entry*(1+best["tp"]) if best["side"]=="LONG" else entry*(1-best["tp"]), "sl": entry*(1-best["sl"]) if best["side"]=="LONG" else entry*(1+best["sl"]), "tp_pct": best["tp"], "sl_pct": best["sl"], "confidence": best["confidence"], "score": best["score"], "reason": best["reason"], "tier": best["tier"], "net_win": best["net_win"]}
                training["open_trades"].append(trade)
                training["real_cap_used"]+=qty
                training["total_volume"]+=qty
                training["best_penny"]=best["symbol"]
                print(f"[{datetime.now().strftime('%H:%M:%S')}] v122 BEST AUTO: {best['symbol']} {best['tier']} {best['side']} ${qty} @ {entry:.8f} TP {best['tp']*100:.1f}% SL {best['sl']*100:.1f}% Net ${best['net_win']:.2f} Conf {best['confidence']}% Score {best['score']}", flush=True)
                return best
    return None

def best_loop():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] v122 BEST LOGICAL 12 penny tiered $0.30 x 167 = $50/day started", flush=True)
    while True:
        try:
            do_one_iteration()
            if training["history"]:
                first=datetime.fromisoformat(training["history"][0]["time"])
                hours=max(0.1, (datetime.now()-first).total_seconds()/3600)
                training["trades_per_hour"]=training["total_trades"]/hours
            time.sleep(15)
        except Exception as e:
            print(f"v122 loop error {e}", flush=True)
            time.sleep(10)

@app.route("/")
@app.route("/frontend")
def frontend():
    for p in ["index.html", "../index.html", "./index.html"]:
        if os.path.exists(p):
            with open(p,"r") as f:
                return f.read()
    return "<h1>v122 BEST missing</h1>"

@app.route("/api/training")
def train_api(): return jsonify(training)

@app.route("/api/scan")
def scan_api():
    try:
        btc1m=fetch_klines("BTCUSDT","1m",26)
        c=[float(k[4]) for k in btc1m] if btc1m else [0]
        btc_up = c[-1]>calc_ema(c,21) if len(c)>=21 else True
    except:
        btc_up=True
    results=[scan_best(sym, btc_up) for sym in SYMBOLS]
    return jsonify({"btc_up": btc_up, "results": results, "training": training})

@app.route("/api/cron")
def cron_api():
    training["last_cron"]=datetime.now().isoformat()
    training["cron_count"]+=1
    best = do_one_iteration()
    if training["history"]:
        first=datetime.fromisoformat(training["history"][0]["time"])
        hours=max(0.1, (datetime.now()-first).total_seconds()/3600)
        training["trades_per_hour"]=training["total_trades"]/hours
    if best:
        return jsonify({"cron": "traded", "symbol": best["symbol"], "tier": best["tier"], "side": best["side"], "qty": best["order_size"], "net_win": best["net_win"], "score": best["score"], "daily": training["daily_pnl"], "open": len(training["open_trades"]), "count": training["cron_count"]})
    return jsonify({"cron": "checked", "open": len(training["open_trades"]), "daily": training["daily_pnl"], "total": training["total_trades"], "count": training["cron_count"], "last": training["last_cron"]})

@app.route("/api/auto", methods=["GET","POST"])
def auto_api():
    if request.method=="POST":
        body=request.get_json() or {}
        training["auto_enabled"]=body.get("enabled", True)
        return jsonify({"auto_enabled": training["auto_enabled"]})
    return jsonify({"auto_enabled": training["auto_enabled"]})

if __name__ == "__main__":
    if os.getenv("VERCEL") != "1":
        t=threading.Thread(target=best_loop, daemon=True)
        t.start()
        port=int(os.getenv("PORT",7860))
        print(f"VENUS v122 BEST LOGICAL 12 penny tiered", flush=True)
        app.run(host="0.0.0.0", port=port, debug=False)
