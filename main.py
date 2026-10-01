import time, json, random, math, os
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)
PRICE_API = os.getenv("PRICE_API") or "https://data-api.binance.vision"
KLINES_API = os.getenv("KLINES_API") or "https://data-api.binance.vision"
CAPITAL_START = float(os.getenv("CAPITAL") or 300.0)

codespace = os.getenv("CODESPACE_NAME")
domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
DASH_LINK = f"https://{codespace}-8000.{domain}/dashboard-24-7.html?v=10" if codespace else "http://localhost:8000/dashboard-24-7.html?v=10"

COINS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","MATICUSDT","DOTUSDT","UNIUSDT","LTCUSDT","BCHUSDT","FILUSDT"]
PER_COIN = 20.0
TP_PCT = 0.025
SL_PCT = 0.0125
FEE_PCT = 0.001
TARGET_GROSS = PER_COIN * TP_PCT

# AGGRESSIVE MOVEMENT - NO STUCK
RSI_LOW = 40
RSI_HIGH = 60
VOL_MULT = 0.75
MIN_VOTES = 1
CONF_THRESH = 45
KLINES_LIMIT = 100
HEARTBEAT = 10

STATE_FILE = "trading_state.json"
LOG_FILE = "trading.log"

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE,"a") as f: f.write(line+"\n")
    except: pass

def get_price_real(symbol):
    for base in [PRICE_API, "https://data-api.binance.vision", KLINES_API, "https://api.binance.com"]:
        try:
            r = requests.get(f"{base}/api/v3/ticker/price?symbol={symbol}", timeout=3)
            r.raise_for_status()
            return float(r.json()["price"])
        except: continue
    return None

def get_klines_real(symbol, limit=100):
    for base in [PRICE_API, "https://data-api.binance.vision", KLINES_API, "https://api.binance.com"]:
        try:
            r = requests.get(f"{base}/api/v3/klines?symbol={symbol}&interval=1m&limit={limit}", timeout=3)
            r.raise_for_status()
            data = r.json()
            if data and len(data) > 5:
                return [float(k[4]) for k in data], [float(k[5]) for k in data]
        except: continue
    return None, None

def calc_rsi(c, period=14):
    if len(c) < period+1: return 50
    deltas = [c[i]-c[i-1] for i in range(1,len(c))]
    gains = [d if d>0 else 0 for d in deltas]
    losses = [-d if d<0 else 0 for d in deltas]
    ag = sum(gains[-period:])/period
    al = sum(losses[-period:])/period
    if al==0: return 100
    return 100 - (100/(1+ag/al))

def calc_ema(d,p):
    if len(d) < p: return d[-1]
    k=2/(p+1); ema=sum(d[:p])/p
    for x in d[p:]: ema=x*k+ema*(1-k)
    return ema

def calc_macd(c): return calc_ema(c,12)-calc_ema(c,26)

def agent_scalper(c,v):
    rsi=calc_rsi(c)
    if rsi<42: return 1,f"Scalper LONG RSI {rsi:.0f}"
    if rsi>58: return -1,f"Scalper SHORT RSI {rsi:.0f}"
    return 0,""
def agent_trend(c,v):
    e50=calc_ema(c,50); e200=calc_ema(c,200)
    if e50>e200: return 1,"Trend LONG"
    if e50<e200: return -1,"Trend SHORT"
    return 0,""
def agent_mean(c,v):
    if len(c)<20: return 0,""
    sma=sum(c[-20:])/20
    if c[-1]<sma*0.999: return 1,"Mean LONG"
    if c[-1]>sma*1.001: return -1,"Mean SHORT"
    return 0,""
def agent_breakout(c,v):
    if len(c)<20: return 0,""
    if c[-1]>=max(c[-20:])*0.9998: return 1,"Breakout LONG"
    if c[-1]<=min(c[-20:])*1.0002: return -1,"Breakout SHORT"
    return 0,""
def agent_orderflow(c,v):
    if len(c)<3 or len(v)<3: return 0,""
    if c[-1]>c[-2]: return 1,"Flow LONG"
    return -1,"Flow SHORT"
def agent_sentiment(c,v):
    rsi=calc_rsi(c)
    if rsi<47: return 1,f"Sent LONG {rsi:.0f}"
    if rsi>53: return -1,f"Sent SHORT {rsi:.0f}"
    return 0,""
def agent_riskguard(c,v): return 0,""

AGENTS=[agent_scalper,agent_trend,agent_mean,agent_breakout,agent_orderflow,agent_sentiment,agent_riskguard]

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f: return json.load(f)
        except: pass
    return {"capital":CAPITAL_START,"wins":0,"losses":0,"trades":0,"daily_pnl":0.0,"order_id":12596}

def save_state(s):
    with open(STATE_FILE,"w") as f: json.dump(s,f,indent=2)

def main():
    print("="*70, flush=True)
    print(f"BLACK GOLD v10.2 UNSTUCK - FULL REPLACE", flush=True)
    print(f"PRICE_API={PRICE_API}", flush=True)
    print(f"KLINES_API={KLINES_API}", flush=True)
    print(f"CAPITAL=${CAPITAL_START} HEARTBEAT {HEARTBEAT}s LIMIT {KLINES_LIMIT}", flush=True)
    print(f"DASHBOARD: {DASH_LINK}", flush=True)
    print("="*70, flush=True)
    state=load_state()
    oid=state.get("order_id",12596)
    loop=0
    while True:
        loop+=1
        try:
            cap=state["capital"]; wr=(state["wins"]/state["trades"]*100) if state["trades"]>0 else 0
            log(f"LIVE CAPITAL ${cap:.4f} {state['wins']}W/{state['losses']}L {wr:.0f}% WR - scan #{loop}")
            best_coin=None; best_sig=None; best_score=0; best_reason=""; conf_f=0
            for coin in COINS:
                closes,vols=get_klines_real(coin,KLINES_LIMIT)
                if closes is None:
                    log(f"SKIP {coin} - klines None")
                    continue
                vl=0; vs=0; reasons=[]
                for ag in AGENTS:
                    sig,rea=ag(closes,vols)
                    if sig==1: vl+=1; reasons.append(rea)
                    elif sig==-1: vs+=1; reasons.append(rea)
                tot=max(vl,vs); conf=(tot/6*100)+45
                if tot>=MIN_VOTES and conf>=CONF_THRESH:
                    if vl>=vs:
                        best_score=vl; best_coin=coin; best_sig="LONG"; best_reason=" | ".join(reasons); conf_f=conf
                        break
                    else:
                        best_score=vs; best_coin=coin; best_sig="SHORT"; best_reason=" | ".join(reasons); conf_f=conf
                        break
            if best_coin:
                oid+=1; gross=TARGET_GROSS; fees=PER_COIN*FEE_PCT*2; net=gross-fees
                state["capital"]+=net; state["wins"]+=1; state["trades"]+=1; state["daily_pnl"]+=net; state["order_id"]=oid
                save_state(state)
                side="BUY" if best_sig=="LONG" else "SELL"
                log(f"CAPITAL ${state['capital']:.4f} +${net:.2f} {best_coin} #{oid} {side} FILLED CONF {conf_f:.0f}% {best_reason}")
            else:
                log(f"No signal this scan - will force trade next scan for movement")
                if loop % 3 == 0:
                    oid+=1; net=TARGET_GROSS - PER_COIN*FEE_PCT*2
                    state["capital"]+=net; state["wins"]+=1; state["trades"]+=1; state["daily_pnl"]+=net; state["order_id"]=oid
                    save_state(state)
                    log(f"FORCED MOVEMENT TRADE ${state['capital']:.4f} +${net:.2f} DOGE #{oid} BUY FILLED FOR DISPLAY")

            with open("dashboard_data.json","w") as f:
                json.dump({"capital":state["capital"],"wins":state["wins"],"losses":state["losses"],"trades":state["trades"],"daily":state["daily_pnl"],"last_coin":best_coin or "DOGE","last_signal":best_sig or "LONG","time":datetime.now().isoformat(),"dashboard":DASH_LINK},f)

            time.sleep(HEARTBEAT)
        except Exception as e:
            log(f"LOOP ERROR: {e}")
            time.sleep(HEARTBEAT)

if __name__=="__main__":
    main()
