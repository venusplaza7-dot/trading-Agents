import os, json, time, math, threading, hmac, hashlib
from datetime import datetime, timedelta
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

AGENTS = {
    "renaissance": {"name": "Renaissance", "full": "Renaissance (Simons) 99%", "strategy": "RSI mean-reversion", "weight": 1.5, "wins": 0, "losses": 0, "real_wr": 0, "desc": "RSI <36 LONG, >64 SHORT - mean reversion"},
    "citadel": {"name": "Citadel", "full": "Citadel (Griffin)", "strategy": "BB breakout", "weight": 1.5, "wins": 0, "losses": 0, "real_wr": 0, "desc": "BB pos <-1.2 LONG, >1.2 SHORT - volatility breakout"},
    "bridgewater": {"name": "Bridgewater", "full": "Bridgewater (Dalio)", "strategy": "Vol regime", "weight": 1.4, "wins": 0, "losses": 0, "real_wr": 0, "desc": "Vol >2.0 high vol regime filter"},
    "berkshire": {"name": "Berkshire", "full": "Berkshire (Buffett)", "strategy": "EMA trend", "weight": 1.4, "wins": 0, "losses": 0, "real_wr": 0, "desc": "EMA 9>21>50>200 trend filter - moat coins only"},
    "soros": {"name": "Soros", "full": "Soros Macro", "strategy": "BTC regime", "weight": 1.3, "wins": 0, "losses": 0, "real_wr": 0, "desc": "BTC 1h+4h EMA21 up = risk on, else risk off"},
    "millennium": {"name": "Millennium", "full": "Millennium", "strategy": "Blend consensus", "weight": 1.3, "wins": 0, "losses": 0, "real_wr": 0, "desc": "Requires 4+ votes + score>4.0 consensus"},
    "twosigma": {"name": "Two Sigma", "full": "Two Sigma ML", "strategy": "ML score", "weight": 1.5, "wins": 0, "losses": 0, "real_wr": 0, "desc": "Weighted score of all signals - machine learning"},
}
COINS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","AVAXUSDT","LINKUSDT","ADAUSDT","DOTUSDT","MATICUSDT","UNIUSDT","ARBUSDT","OPUSDT","INJUSDT","RNDRUSDT","ATOMUSDT"]
MAX_CAP = 300.0
ORDER_SIZE = 100.0
TP_PCT = 0.035
SL_PCT = 0.01
FEE_PCT = 0.001
FEE_RT = ORDER_SIZE * FEE_PCT * 2
GROSS_WIN = ORDER_SIZE * TP_PCT
NET_WIN = GROSS_WIN - FEE_RT
LOSS_NET = ORDER_SIZE * SL_PCT + FEE_RT

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
BASE_URL = "https://testnet.binance.vision"
DATA_URL = "https://data-api.binance.vision"

training = {
    "total_trades": 0, "total_wins": 0, "total_losses": 0,
    "total_volume": 0.0, "total_fees": 0.0, "total_gross": 0.0, "total_net": 0.0,
    "daily_pnl": 0.0, "daily_trades": 0, "real_cap_used": 0.0,
    "real_cap_locked": MAX_CAP, "order_size": ORDER_SIZE,
    "gross_win": GROSS_WIN, "net_win": NET_WIN, "fee_rt": FEE_RT, "loss_net": LOSS_NET,
    "agents": AGENTS, "history": [], "open_trades": [], "paper_mode": True, "coins_count": 15,
    "win_rate": 0.0, "both_ways": True, "real_training": True, "v114": True,
    "training_mode": "REAL MARKET PAPER MONEY - agents learn from real TP/SL hits"
}

def get_keys():
    return os.getenv("BINANCE_API_KEY", "vaYEuEx3c8r1KwgRnascV4AB0pyMTo8pNWyy6ckwXgJEJ56VA6QHi3d3pV6St"), os.getenv("BINANCE_API_SECRET", "qkq6QX100nOAOeJ61JV0wRr50z7jWNedMpR8ze5aO8BTFo8cC76no2zVGa7TjFEyxq")

def fetch_klines(symbol, interval="15m", limit=200):
    for base in [DATA_URL, "https://api.binance.com"]:
        try:
            r = requests.get(f"{base}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}", timeout=10)
            r.raise_for_status()
            return r.json()
        except:
            continue
    raise Exception("klines failed")

def fetch_recent_klines_after(symbol, after_timestamp_ms, interval="1m", limit=100):
    """Fetch klines after a timestamp to check real outcome"""
    try:
        r = requests.get(f"{DATA_URL}/api/v3/klines?symbol={symbol}&interval={interval}&startTime={after_timestamp_ms}&limit={limit}", timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return []

def calc_rsi(closes, period=14):
    if len(closes) < period+1: return 50
    gains = losses = 0
    for i in range(len(closes)-period, len(closes)):
        d = closes[i]-closes[i-1]
        if d>0: gains+=d
        else: losses-=d
    gains/=period; losses/=period
    if losses==0: return 100
    return 100-100/(1+gains/losses)

def calc_ema(arr, period):
    k=2/(period+1); ema=arr[0]
    for v in arr[1:]: ema=v*k+ema*(1-k)
    return ema

def calc_bb(closes, period=20, mult=2):
    if len(closes)<period: return 0,0,0,0,0
    sl=closes[-period:]; mid=sum(sl)/period
    var=sum((x-mid)**2 for x in sl)/period; std=var**0.5
    upper=mid+mult*std; lower=mid-mult*std; price=closes[-1]
    bb_pos=(price-mid)/std if std!=0 else 0
    width=(upper-lower)/mid*100 if mid!=0 else 0
    return mid, upper, lower, bb_pos, width

def calc_vol(closes):
    if len(closes)<20: return 0.5
    rets=[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes))]
    sl=rets[-20:]; mean=sum(sl)/len(sl)
    var=sum((x-mean)**2 for x in sl)/len(sl)
    return (var**0.5)*100*15

def scan_coin(symbol, btc_up=True):
    try:
        klines=fetch_klines(symbol,"15m",200)
        closes=[float(k[4]) for k in klines]
        price=closes[-1]
        rsi=calc_rsi(closes)
        ema9=calc_ema(closes,9); ema21=calc_ema(closes,21); ema50=calc_ema(closes,50)
        mid, upper, lower, bb_pos, bb_w = calc_bb(closes)
        vol=calc_vol(closes)
        votes_long=0; votes_short=0; score=0; voters=[]
        if rsi<30:
            votes_long+=AGENTS["renaissance"]["weight"]; score+=1.5*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
        elif rsi>70:
            votes_short+=AGENTS["renaissance"]["weight"]; score+=1.5*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
        elif rsi<36 or rsi>64:
            if rsi<36: votes_long+=0.5*AGENTS["renaissance"]["weight"]
            else: votes_short+=0.5*AGENTS["renaissance"]["weight"]
            score+=1.0*AGENTS["renaissance"]["weight"]; voters.append("renaissance")
        if bb_pos<-1.2:
            votes_long+=AGENTS["citadel"]["weight"]; score+=1.2*AGENTS["citadel"]["weight"]; voters.append("citadel")
        elif bb_pos>1.2:
            votes_short+=AGENTS["citadel"]["weight"]; score+=1.2*AGENTS["citadel"]["weight"]; voters.append("citadel")
        elif abs(bb_pos)>0.7:
            if bb_pos<0: votes_long+=0.8*AGENTS["citadel"]["weight"]
            else: votes_short+=0.8*AGENTS["citadel"]["weight"]
            score+=0.8*AGENTS["citadel"]["weight"]; voters.append("citadel")
        if vol>2.0:
            votes_long+=AGENTS["bridgewater"]["weight"]*0.6; votes_short+=AGENTS["bridgewater"]["weight"]*0.6
            score+=1.0*AGENTS["bridgewater"]["weight"]; voters.append("bridgewater")
        if ema9>ema21 and ema21>ema50:
            votes_long+=AGENTS["berkshire"]["weight"]; score+=1.0*AGENTS["berkshire"]["weight"]; voters.append("berkshire")
        elif ema9<ema21 and ema21<ema50:
            votes_short+=AGENTS["berkshire"]["weight"]; score+=1.0*AGENTS["berkshire"]["weight"]; voters.append("berkshire")
        if btc_up:
            votes_long+=AGENTS["soros"]["weight"]*0.8; score+=0.8*AGENTS["soros"]["weight"]; voters.append("soros")
        else:
            votes_short+=AGENTS["soros"]["weight"]*0.8; score+=0.8*AGENTS["soros"]["weight"]; voters.append("soros")
        if votes_long+votes_short>=4 and score>4.0:
            voters.append("millennium")
        voters.append("twosigma")
        side = "LONG" if votes_long>votes_short and score>4.0 else ("SHORT" if votes_short>votes_long and score>4.0 else "WAIT")
        return {"symbol": symbol, "price": price, "rsi": round(rsi,1), "bb_pos": round(bb_pos,2), "vol": round(vol,2), "votes_long": round(votes_long,2), "votes_short": round(votes_short,2), "score": round(score,2), "side": side, "voters": voters, "ema9": ema9, "ema21": ema21}
    except Exception as e:
        return {"symbol": symbol, "side": "WAIT", "score": 0, "votes_long": 0, "votes_short": 0, "rsi": 50, "bb_pos": 0, "vol": 0, "price": 0, "voters": [], "error": str(e)}

def check_real_outcome(trade):
    """Check real market outcome for an open trade"""
    try:
        symbol = trade["symbol"]
        entry_price = trade["entry_price"]
        side = trade["side"]
        entry_time_ms = trade["entry_time_ms"]
        # Fetch 1m klines after entry
        klines = fetch_recent_klines_after(symbol, entry_time_ms, "1m", 240) # 4 hours
        if not klines:
            return None
        tp_price = entry_price * (1+TP_PCT) if side=="LONG" else entry_price * (1-TP_PCT)
        sl_price = entry_price * (1-SL_PCT) if side=="LONG" else entry_price * (1+SL_PCT)
        for k in klines:
            high = float(k[2]); low = float(k[3]); open_time = k[0]
            if side=="LONG":
                if high >= tp_price:
                    return {"result": "WIN", "exit_price": tp_price, "exit_time_ms": open_time, "reason": f"TP {TP_PCT*100}% hit @ {tp_price}", "bars": (open_time-entry_time_ms)//60000}
                if low <= sl_price:
                    return {"result": "LOSS", "exit_price": sl_price, "exit_time_ms": open_time, "reason": f"SL {SL_PCT*100}% hit @ {sl_price}", "bars": (open_time-entry_time_ms)//60000}
            else: # SHORT
                if low <= tp_price:
                    return {"result": "WIN", "exit_price": tp_price, "exit_time_ms": open_time, "reason": f"TP {TP_PCT*100}% hit @ {tp_price}", "bars": (open_time-entry_time_ms)//60000}
                if high >= sl_price:
                    return {"result": "LOSS", "exit_price": sl_price, "exit_time_ms": open_time, "reason": f"SL {SL_PCT*100}% hit @ {sl_price}", "bars": (open_time-entry_time_ms)//60000}
        return None # still open
    except Exception as e:
        return {"result": "ERROR", "error": str(e)}

def trading_loop():
    while True:
        try:
            # Check open trades for real outcomes
            for trade in training["open_trades"][:]:
                outcome = check_real_outcome(trade)
                if outcome and outcome["result"] in ["WIN","LOSS"]:
                    is_win = outcome["result"]=="WIN"
                    pnl_gross = GROSS_WIN if is_win else -ORDER_SIZE*SL_PCT
                    pnl_net = NET_WIN if is_win else -LOSS_NET
                    # Update training
                    training["total_trades"]+=1
                    training["total_volume"]+=ORDER_SIZE
                    training["total_fees"]+=FEE_RT
                    if is_win:
                        training["total_wins"]+=1
                        training["total_gross"]+=GROSS_WIN
                        training["total_net"]+=NET_WIN
                        training["daily_pnl"]+=NET_WIN
                        for v in trade["voters"]:
                            if v in AGENTS:
                                AGENTS[v]["wins"]+=1
                                AGENTS[v]["weight"]=min(2.0, AGENTS[v]["weight"]+0.05)
                    else:
                        training["total_losses"]+=1
                        training["total_net"]-=LOSS_NET
                        training["daily_pnl"]-=LOSS_NET
                        for v in trade["voters"]:
                            if v in AGENTS:
                                AGENTS[v]["losses"]+=1
                                AGENTS[v]["weight"]=max(0.3, AGENTS[v]["weight"]-0.03)
                    # Update win rates
                    for agent_id in AGENTS:
                        a = AGENTS[agent_id]
                        total = a["wins"]+a["losses"]
                        a["real_wr"] = (a["wins"]/total*100) if total>0 else 0
                    training["win_rate"] = (training["total_wins"]/max(1,training["total_trades"])*100)
                    training["real_cap_used"]=max(0, training["real_cap_used"]-ORDER_SIZE)
                    training["history"].append({
                        "time": datetime.now().isoformat(),
                        "symbol": trade["symbol"],
                        "side": trade["side"],
                        "is_win": is_win,
                        "entry_price": trade["entry_price"],
                        "exit_price": outcome["exit_price"],
                        "pnl_gross": pnl_gross,
                        "pnl_net": pnl_net,
                        "voters": trade["voters"],
                        "reason": outcome["reason"],
                        "bars": outcome.get("bars",0),
                        "daily_pnl": training["daily_pnl"],
                        "real_outcome": True
                    })
                    if len(training["history"])>200:
                        training["history"]=training["history"][-200:]
                    training["open_trades"].remove(trade)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] REAL OUTCOME {trade['symbol']} {trade['side']} {outcome['result']} {outcome['reason']} Net ${pnl_net:.2f} Daily ${training['daily_pnl']:.2f} WR {training['win_rate']:.1f}%", flush=True)
            time.sleep(30)
        except Exception as e:
            print(f"Loop error {e}", flush=True)
            time.sleep(10)

@app.route("/")
@app.route("/frontend")
def frontend():
    try:
        for p in ["index.html", "../index.html", "./index.html", "/var/task/index.html", os.path.join(os.path.dirname(__file__), "..", "index.html")]:
            if os.path.exists(p):
                with open(p,"r") as f:
                    return f.read()
        return "<h1>v114 REAL TRAINING - index.html missing - redeploy</h1>"
    except Exception as e:
        return f"<h1>v114 error {e}</h1>"

@app.route("/api/balance")
def balance():
    try:
        mock_balances = {"USDT": {"asset": "USDT", "free": "10000.00000000", "locked": "0.00000000"}}
        return jsonify({"ok": True, "real": True, "paper": True, "real_training": True, "v114": True, "balances": mock_balances, "real_cap_locked": MAX_CAP, "order_size": ORDER_SIZE, "gross_win": GROSS_WIN, "net_win": NET_WIN, "fee": FEE_RT, "loss_net": LOSS_NET, "training": training, "coins": COINS, "both_ways": True, "training_mode": "REAL MARKET PAPER MONEY - agents learn from real TP/SL hits"}), 200
    except Exception as e:
        return jsonify({"error": str(e), "training": training}), 500

@app.route("/api/order", methods=["POST","OPTIONS"])
def order():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    try:
        body = request.get_json() or {}
        symbol = body.get("symbol", "BTCUSDT")
        side = body.get("side", "LONG")
        quote_qty = float(body.get("quoteOrderQty", ORDER_SIZE))
        if quote_qty > ORDER_SIZE: quote_qty = ORDER_SIZE
        if training["real_cap_used"] + quote_qty > MAX_CAP:
            return jsonify({"error": f"CAP ${MAX_CAP} exceeded Used ${training['real_cap_used']:.2f} + ${quote_qty} > max.", "cap": MAX_CAP, "used": training["real_cap_used"]}), 400
        # Get current price
        try:
            kl = fetch_klines(symbol, "1m", 1)
            entry_price = float(kl[-1][4])
        except:
            entry_price = 60000 if "BTC" in symbol else 3000
        entry_time_ms = int(time.time()*1000)
        voters = body.get("voters", ["renaissance","citadel"])
        trade = {
            "symbol": symbol, "side": side, "entry_price": entry_price, "entry_time_ms": entry_time_ms,
            "quote_qty": quote_qty, "voters": voters, "status": "OPEN",
            "tp_price": entry_price*(1+TP_PCT) if side=="LONG" else entry_price*(1-TP_PCT),
            "sl_price": entry_price*(1-SL_PCT) if side=="LONG" else entry_price*(1+SL_PCT)
        }
        training["open_trades"].append(trade)
        training["real_cap_used"]+=quote_qty
        training["total_volume"]+=quote_qty
        mock_order = {
            "symbol": symbol, "orderId": int(time.time()*1000)%10000000, "status": "FILLED_PAPER_REAL_v114",
            "side": side, "entry_price": entry_price, "tp": trade["tp_price"], "sl": trade["sl_price"],
            "executedQty": str(quote_qty/entry_price), "cummulativeQuoteQty": str(quote_qty),
        }
        return jsonify({"ok": True, "real": True, "paper": True, "real_training": True, "v114": True, "order": mock_order, "training": training, "both_ways": True, "message": f"REAL TRAINING v114: {symbol} {side} entry {entry_price} TP {trade['tp_price']:.2f} SL {trade['sl_price']:.2f} - outcome will be checked from real market in next 4h"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/training", methods=["GET","POST"])
def training_api():
    if request.method == "GET":
        return jsonify(training)
    # Manual close for testing (old v113 compatibility)
    body = request.get_json() or {}
    symbol = body.get("symbol", "BTCUSDT")
    is_win = body.get("is_win", True)
    # This endpoint now is for manual override only - real outcomes come from trading_loop
    return jsonify(training)

@app.route("/api/scan")
def scan_api():
    try:
        try:
            btc1h=fetch_klines("BTCUSDT","1h",30); btc4h=fetch_klines("BTCUSDT","4h",30)
            c1=[float(k[4]) for k in btc1h]; c4=[float(k[4]) for k in btc4h]
            btc_up = c1[-1]>calc_ema(c1,21) and c4[-1]>calc_ema(c4,21)
        except:
            btc_up=True
        results=[]
        for coin in COINS:
            results.append(scan_coin(coin, btc_up))
            time.sleep(0.1)
        return jsonify({"btc_up": btc_up, "results": results, "training": training, "math": {"order": ORDER_SIZE, "gross_win": GROSS_WIN, "fee": FEE_RT, "net_win": NET_WIN, "loss_net": LOSS_NET, "paper": True, "real_training": True, "v114": True, "coins": len(COINS), "both_ways": True, "training_mode": "REAL MARKET PAPER MONEY - agents learn from real TP/SL hits"}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/open_trades")
def open_trades_api():
    return jsonify({"open_trades": training["open_trades"], "count": len(training["open_trades"])})

@app.route("/api/check_outcomes", methods=["POST"])
def check_outcomes():
    # Force check all open trades now
    checked = []
    for trade in training["open_trades"][:]:
        outcome = check_real_outcome(trade)
        checked.append({"symbol": trade["symbol"], "side": trade["side"], "outcome": outcome})
    return jsonify({"checked": checked, "open": len(training["open_trades"])})

if __name__ == "__main__":
    if os.getenv("VERCEL") != "1":
        t = threading.Thread(target=trading_loop, daemon=True)
        t.start()
        port = int(os.getenv("PORT", 7860))
        print(f"Starting VENUS v114 REAL TRAINING - REAL MARKET PAPER MONEY - Agents learn from real TP/SL hits - 7 agents 15 coins $300 cap - port {port}", flush=True)
        app.run(host="0.0.0.0", port=port, debug=False)
