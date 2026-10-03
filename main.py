import os, json, time, math, threading
from datetime import datetime
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

PENNY_COINS = [
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT",
    "WIFUSDT", "MEMEUSDT", "BOMEUSDT", "1000PEPEUSDT", "1000SHIBUSDT",
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT"
]
MAX_CAP = 300.0
DAILY_GOAL = 50.0
BASE_ORDER = 30.0
MIN_ORDER = 25.0
MAX_ORDER = 60.0
TP_PCT = 0.012  # 1.2% TP = $30*0.012=$0.36 gross - $0.06 fee = $0.30 net WIN
SL_PCT = 0.006  # 0.6% SL = $0.18 loss + $0.06 fee = $0.24 LOSS
FEE_PCT = 0.001
NET_WIN = BASE_ORDER * TP_PCT - BASE_ORDER*FEE_PCT*2  # $0.30
NET_LOSS = BASE_ORDER * SL_PCT + BASE_ORDER*FEE_PCT*2 # $0.24
RR = NET_WIN/NET_LOSS  # 1.25:1, need 44% WR break even

AGENTS = {
    "renaissance": {"name": "Renaissance", "weight": 1.5, "wins": 0, "losses": 0, "profit": 0.0, "desc": "RSI penny - RSI<35 LONG >65 SHORT - mean reversion", "wr": 0},
    "citadel": {"name": "Citadel", "weight": 1.6, "wins": 0, "losses": 0, "profit": 0.0, "desc": "BB breakout - BB<-1.2 LONG >1.2 SHORT - volatility", "wr": 0},
    "bridgewater": {"name": "Bridgewater", "weight": 1.6, "wins": 0, "losses": 0, "profit": 0.0, "desc": "Vol spike - penny pump detector Vol>2.5x", "wr": 0},
    "berkshire": {"name": "Berkshire", "weight": 1.4, "wins": 0, "losses": 0, "profit": 0.0, "desc": "EMA trend - 9>21>50 = trend", "wr": 0},
    "soros": {"name": "Soros", "weight": 1.4, "wins": 0, "losses": 0, "profit": 0.0, "desc": "BTC regime - BTC up = risk on", "wr": 0},
    "millennium": {"name": "Millennium", "weight": 1.4, "wins": 0, "losses": 0, "profit": 0.0, "desc": "Consensus 4+ votes + score>4.5", "wr": 0},
    "twosigma": {"name": "Two Sigma", "weight": 1.6, "wins": 0, "losses": 0, "profit": 0.0, "desc": "ML score combines all - machine learning", "wr": 0},
}

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
DATA_URL = "https://data-api.binance.vision"

training = {
    "total_trades": 0, "total_wins": 0, "total_losses": 0,
    "total_volume": 0.0, "total_fees": 0.0, "total_net": 0.0,
    "daily_pnl": 0.0, "real_cap_used": 0.0, "daily_goal": DAILY_GOAL,
    "agents": AGENTS, "history": [], "open_trades": [],
    "win_rate": 0.0, "auto_enabled": True, "v120": True,
    "mode": "OPTION B PENNY $0.30 x 200 wins = $50/day - MOST LOGICAL for $300",
    "net_win": NET_WIN, "net_loss": NET_LOSS, "rr": RR, "tp": TP_PCT, "sl": SL_PCT,
    "trades_per_hour": 0, "trades_per_day_max": 0, "best_penny": None,
    "penny_coins": PENNY_COINS, "cap": MAX_CAP, "order": BASE_ORDER
}

def fetch_klines(symbol, interval="1m", limit=120):
    for base in [DATA_URL, "https://api.binance.com"]:
        try:
            r = requests.get(f"{base}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}", timeout=8)
            r.raise_for_status()
            return r.json()
        except:
            continue
    return []

def fetch_after(symbol, after_ms, limit=400):
    try:
        r = requests.get(f"{DATA_URL}/api/v3/klines?symbol={symbol}&interval=1m&startTime={after_ms}&limit={limit}", timeout=8)
        r.raise_for_status()
        return r.json()
    except:
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
    rets=[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]
    sl=rets[-20:]; mean=sum(sl)/len(sl)
    var=sum((x-mean)**2 for x in sl)/len(sl)
    return (var**0.5)*100*5

def scan_penny(symbol, btc_up=True):
    try:
        klines=fetch_klines(symbol,"1m",120)
        if not klines: return {"symbol": symbol, "side": "WAIT", "score": 0, "price": 0, "voters": [], "confidence": 0, "order_size": BASE_ORDER, "rsi": 50, "bb_pos": 0, "vol": 0, "is_penny": False}
        closes=[float(k[4]) for k in klines]
        price=closes[-1]
        rsi=calc_rsi(closes)
        ema9=calc_ema(closes,9); ema21=calc_ema(closes,21); ema50=calc_ema(closes,50)
        mid, up, lo, bb_pos, bb_w = calc_bb(closes)
        vol=calc_vol(closes)
        is_penny = any(x in symbol for x in ["PEPE","SHIB","FLOKI","BONK","DOGE","MEME","BOME","WIF","1000"])
        votes_long=0; votes_short=0; score=0; voters=[]
        # Option B thresholds - slightly higher than A for better quality
        if is_penny:
            if rsi<30: votes_long+=AGENTS["renaissance"]["weight"]*1.5; score+=1.8*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi>70: votes_short+=AGENTS["renaissance"]["weight"]*1.5; score+=1.8*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi<38: votes_long+=AGENTS["renaissance"]["weight"]; score+=1.1*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi>62: votes_short+=AGENTS["renaissance"]["weight"]; score+=1.1*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
        else:
            if rsi<35: votes_long+=AGENTS["renaissance"]["weight"]; score+=1.2*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
            elif rsi>65: votes_short+=AGENTS["renaissance"]["weight"]; score+=1.2*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
        if bb_pos<-1.2: votes_long+=AGENTS["citadel"]["weight"]*1.3; score+=1.5*AGENTS["citadel"]["weight"]; voters.append("citadel")
        elif bb_pos>1.2: votes_short+=AGENTS["citadel"]["weight"]*1.3; score+=1.5*AGENTS["citadel"]["weight"]; voters.append("citadel")
        elif abs(bb_pos)>0.8:
            if bb_pos<0: votes_long+=AGENTS["citadel"]["weight"]
            else: votes_short+=AGENTS["citadel"]["weight"]
            score+=1.0*AGENTS["citadel"]["weight"]; voters.append("citadel")
        if vol>2.5: votes_long+=AGENTS["bridgewater"]["weight"]; votes_short+=AGENTS["bridgewater"]["weight"]; score+=1.3*AGENTS["bridgewater"]["weight"]; voters.append("bridgewater")
        elif vol>1.8: score+=0.7*AGENTS["bridgewater"]["weight"]; voters.append("bridgewater")
        if ema9>ema21 and ema21>ema50: votes_long+=AGENTS["berkshire"]["weight"]; score+=1.0*AGENTS["berkshire"]["weight"]; voters.append("berkshire")
        elif ema9<ema21 and ema21<ema50: votes_short+=AGENTS["berkshire"]["weight"]; score+=1.0*AGENTS["berkshire"]["weight"]; voters.append("berkshire")
        if btc_up: votes_long+=AGENTS["soros"]["weight"]*0.6; score+=0.6*AGENTS["soros"]["weight"]; voters.append("soros")
        else: votes_short+=AGENTS["soros"]["weight"]*0.6; score+=0.6*AGENTS["soros"]["weight"]; voters.append("soros")
        if votes_long+votes_short>=4 and score>4.5: score+=0.8*AGENTS["millennium"]["weight"]; voters.append("millennium")
        voters.append("twosigma")
        side = "LONG" if votes_long>votes_short and score>=4.0 else ("SHORT" if votes_short>votes_long and score>=4.0 else "WAIT")
        conf = min(95, (score/7)*100)
        avg_w = sum([AGENTS[v]["weight"] for v in voters if v in AGENTS])/max(1,len([v for v in voters if v in AGENTS]))
        order_size = BASE_ORDER + (score-4.0)*6 + (avg_w-1)*6
        order_size = max(MIN_ORDER, min(MAX_ORDER, order_size))
        order_size = round(order_size/5)*5
        if is_penny: order_size = min(MAX_ORDER, order_size+5)
        return {"symbol": symbol, "price": price, "rsi": round(rsi,1), "bb_pos": round(bb_pos,2), "vol": round(vol,2), "votes_long": round(votes_long,2), "votes_short": round(votes_short,2), "score": round(score,2), "side": side, "voters": voters, "confidence": round(conf,1), "order_size": order_size, "is_penny": is_penny, "reason": f"RSI {rsi:.1f} BB {bb_pos:.2f} Vol {vol:.1f}x {'PENNY' if is_penny else ''} Score {score:.1f}"}
    except Exception as e:
        return {"symbol": symbol, "side": "WAIT", "score": 0, "price": 0, "voters": [], "confidence": 0, "order_size": BASE_ORDER, "rsi": 50, "bb_pos": 0, "vol": 0, "is_penny": False, "error": str(e)}

def check_outcome(trade):
    try:
        symbol=trade["symbol"]; entry=trade["entry_price"]; side=trade["side"]; after=trade["entry_time_ms"]; qty=trade["quote_qty"]
        klines=fetch_after(symbol, after, 500)
        if not klines: return None
        tp = entry*(1+TP_PCT) if side=="LONG" else entry*(1-TP_PCT)
        sl = entry*(1-SL_PCT) if side=="LONG" else entry*(1+SL_PCT)
        fee = qty*FEE_PCT*2
        gross_win = qty*TP_PCT
        net_win = gross_win - fee
        loss_net = qty*SL_PCT + fee
        for k in klines:
            high=float(k[2]); low=float(k[3]); ot=k[0]
            if side=="LONG":
                if high>=tp: return {"result": "WIN", "exit": tp, "ot": ot, "bars": (ot-after)//60000, "gross": gross_win, "net": net_win, "fee": fee, "reason": f"TP +{TP_PCT*100:.1f}% = ${net_win:.2f}"}
                if low<=sl: return {"result": "LOSS", "exit": sl, "ot": ot, "bars": (ot-after)//60000, "gross": -qty*SL_PCT, "net": -loss_net, "fee": fee, "reason": f"SL -{SL_PCT*100:.1f}% = -${loss_net:.2f}"}
            else:
                if low<=tp: return {"result": "WIN", "exit": tp, "ot": ot, "bars": (ot-after)//60000, "gross": gross_win, "net": net_win, "fee": fee, "reason": f"TP -{TP_PCT*100:.1f}% = ${net_win:.2f}"}
                if high>=sl: return {"result": "LOSS", "exit": sl, "ot": ot, "bars": (ot-after)//60000, "gross": -qty*SL_PCT, "net": -loss_net, "fee": fee, "reason": f"SL +{SL_PCT*100:.1f}% = -${loss_net:.2f}"}
        return None
    except:
        return None

def optionB_loop():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] v120 OPTION B $0.30 x 200 = $50/day MOST LOGICAL for $300", flush=True)
    while True:
        try:
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
                                AGENTS[v]["weight"]=min(2.0, AGENTS[v]["weight"]+0.035)
                    else:
                        training["total_losses"]+=1
                        for v in trade["voters"]:
                            if v in AGENTS:
                                AGENTS[v]["losses"]+=1
                                AGENTS[v]["profit"]+=out["net"]/len(trade["voters"])
                                AGENTS[v]["weight"]=max(0.5, AGENTS[v]["weight"]-0.02)
                    for aid in AGENTS:
                        a=AGENTS[aid]; tot=a["wins"]+a["losses"]; a["wr"]=(a["wins"]/tot*100) if tot>0 else 0
                    training["win_rate"]=(training["total_wins"]/max(1,training["total_trades"])*100)
                    training["real_cap_used"]=max(0, training["real_cap_used"]-trade["quote_qty"])
                    training["history"].append({"time": datetime.now().isoformat(), "symbol": trade["symbol"], "side": trade["side"], "is_win": is_win, "entry": trade["entry_price"], "exit": out["exit"], "pnl_net": out["net"], "qty": trade["quote_qty"], "voters": trade["voters"], "reason": out["reason"], "bars": out["bars"], "daily": training["daily_pnl"], "is_penny": trade.get("is_penny", False)})
                    if len(training["history"])>400: training["history"]=training["history"][-400:]
                    training["open_trades"].remove(trade)
                    need = max(0, int((DAILY_GOAL-training["daily_pnl"])/NET_WIN)) if NET_WIN>0 else 0
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] OPTION B {trade['symbol']} {trade['side']} {out['result']} ${out['net']:.2f} {out['reason']} Daily ${training['daily_pnl']:.2f} WR {training['win_rate']:.1f}% Need {need}x $0.30 for $50", flush=True)

            if training["auto_enabled"] and training["daily_pnl"] < DAILY_GOAL and len(training["open_trades"]) < 10 and training["real_cap_used"] < MAX_CAP*0.97:
                try:
                    btc1m=fetch_klines("BTCUSDT","1m",26)
                    c=[float(k[4]) for k in btc1m] if btc1m else [0]
                    btc_up = c[-1]>calc_ema(c,21) if len(c)>=21 else True
                except:
                    btc_up=True
                results=[]
                for coin in PENNY_COINS:
                    if any(t["symbol"]==coin for t in training["open_trades"]):
                        continue
                    results.append(scan_penny(coin, btc_up))
                signals=[r for r in results if r["side"]!="WAIT" and r["score"]>=4.0 and r["confidence"]>=52]
                signals.sort(key=lambda x: (1.25 if x["is_penny"] else 1.0)*x["score"]*x["confidence"], reverse=True)
                if signals:
                    best=signals[0]
                    qty=best["order_size"]
                    if training["real_cap_used"]+qty>MAX_CAP:
                        qty=MAX_CAP-training["real_cap_used"]
                    if qty>=MIN_ORDER:
                        kl=fetch_klines(best["symbol"],"1m",1)
                        entry=float(kl[-1][4]) if kl else best["price"]
                        trade={"symbol": best["symbol"], "side": best["side"], "entry_price": entry, "entry_time_ms": int(time.time()*1000), "quote_qty": qty, "voters": best["voters"], "tp": entry*(1+TP_PCT) if best["side"]=="LONG" else entry*(1-TP_PCT), "sl": entry*(1-SL_PCT) if best["side"]=="LONG" else entry*(1+SL_PCT), "confidence": best["confidence"], "score": best["score"], "reason": best["reason"], "is_penny": best["is_penny"]}
                        training["open_trades"].append(trade)
                        training["real_cap_used"]+=qty
                        training["total_volume"]+=qty
                        training["best_penny"]=best["symbol"]
                        need = max(0, int((DAILY_GOAL-training["daily_pnl"])/NET_WIN))
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] OPTION B AUTO: {best['symbol']} {best['side']} ${qty} @ {entry:.6f} TP {trade['tp']:.6f} SL {trade['sl']:.6f} Conf {best['confidence']}% Score {best['score']} {'PENNY' if best['is_penny'] else ''} Need {need}x $0.30 for $50", flush=True)

            if training["history"]:
                first=datetime.fromisoformat(training["history"][0]["time"])
                hours=max(0.1, (datetime.now()-first).total_seconds()/3600)
                training["trades_per_hour"]=training["total_trades"]/hours
                training["trades_per_day_max"]=training["trades_per_hour"]*24

            time.sleep(18)
        except Exception as e:
            print(f"Option B loop error {e}", flush=True)
            time.sleep(10)

@app.route("/")
@app.route("/frontend")
def frontend():
    for p in ["index.html", "../index.html", "./index.html"]:
        if os.path.exists(p):
            with open(p,"r") as f:
                return f.read()
    return "<h1>v120 OPTION B missing</h1>"

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
    results=[scan_penny(coin, btc_up) for coin in PENNY_COINS]
    need = max(0, int((DAILY_GOAL-training["daily_pnl"])/NET_WIN)) if NET_WIN>0 else 0
    return jsonify({"btc_up": btc_up, "results": results, "training": training, "optionB": {"tp": TP_PCT, "sl": SL_PCT, "net_win": NET_WIN, "net_loss": NET_LOSS, "rr": RR, "goal": DAILY_GOAL, "need_wins": need, "order": BASE_ORDER}})

@app.route("/api/check_outcomes", methods=["POST"])
def check_api():
    checked=[]
    for trade in training["open_trades"][:]:
        out=check_outcome(trade)
        checked.append({"symbol": trade["symbol"], "side": trade["side"], "outcome": out})
    return jsonify({"checked": checked})

@app.route("/api/auto", methods=["GET","POST"])
def auto_api():
    if request.method=="POST":
        body=request.get_json() or {}
        training["auto_enabled"]=body.get("enabled", True)
        return jsonify({"auto_enabled": training["auto_enabled"]})
    return jsonify({"auto_enabled": training["auto_enabled"]})

if __name__ == "__main__":
    if os.getenv("VERCEL") != "1":
        t=threading.Thread(target=optionB_loop, daemon=True)
        t.start()
        port=int(os.getenv("PORT",7860))
        print(f"VENUS v120 OPTION B $0.30 x 200 = $50/day MOST LOGICAL", flush=True)
        app.run(host="0.0.0.0", port=port, debug=False)
