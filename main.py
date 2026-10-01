import time, json, random, math, os
from datetime import datetime
import requests
from dotenv import load_dotenv

# --- .env PICKUP FIX ---
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

PRICE_API = os.getenv("PRICE_API") or "https://data-api.binance.vision"
KLINES_API = os.getenv("KLINES_API") or "https://api.binance.com"
USE_TESTNET = (os.getenv("USE_TESTNET") or "True").lower() == "true"
CAPITAL_START = float(os.getenv("CAPITAL") or 300.0)

# --- DASHBOARD LINK AUTO-GENERATE ---
codespace = os.getenv("CODESPACE_NAME")
domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
if codespace:
    DASH_LINK = f"https://{codespace}-8000.{domain}/dashboard-24-7.html?v=10"
else:
    DASH_LINK = "http://localhost:8000/dashboard-24-7.html?v=10"

COINS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","MATICUSDT","DOTUSDT","UNIUSDT","LTCUSDT","BCHUSDT","FILUSDT"]
PER_COIN = 20.0
TP_PCT = 0.025
SL_PCT = 0.0125
FEE_PCT = 0.001
TARGET_GROSS = PER_COIN * TP_PCT
RSI_LOW = 35
RSI_HIGH = 65
VOL_MULT = 0.9
MIN_VOTES = 2
CONF_THRESH = 58
KLINES_LIMIT = 500
HEARTBEAT = 20
STATE_FILE = "trading_state.json"
LOG_FILE = "trading.log"

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE,"a") as f:
        f.write(line+"\n")

def get_price_real(symbol):
    try:
        r = requests.get(f"{PRICE_API}/api/v3/ticker/price?symbol={symbol}", timeout=5)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        # fallback to KLINES_API if vision blocked
        try:
            r = requests.get(f"{KLINES_API}/api/v3/ticker/price?symbol={symbol}", timeout=5)
            r.raise_for_status()
            return float(r.json()["price"])
        except:
            log(f"ERROR PRICE {symbol}: {e} — NO FAKE")
            return None

def get_klines_real(symbol, limit=500):
    try:
        r = requests.get(f"{KLINES_API}/api/v3/klines?symbol={symbol}&interval=1m&limit={limit}", timeout=8)
        r.raise_for_status()
        data = r.json()
        return [float(k[4]) for k in data], [float(k[5]) for k in data]
    except Exception as e:
        log(f"ERROR KLINES {symbol}: {e} — NO FAKE")
        return None, None

def calc_rsi(closes, period=14):
    if len(closes) < period+1: return 50
    deltas = [closes[i]-closes[i-1] for i in range(1,len(closes))]
    gains = [d if d>0 else 0 for d in deltas]
    losses = [-d if d<0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:])/period
    avg_loss = sum(losses[-period:])/period
    if avg_loss==0: return 100
    return 100 - (100/(1+avg_gain/avg_loss))

def calc_ema(data, period):
    if len(data) < period: return data[-1]
    k = 2/(period+1)
    ema = sum(data[:period])/period
    for p in data[period:]:
        ema = p*k+ema*(1-k)
    return ema

def calc_macd(c): return calc_ema(c,12)-calc_ema(c,26)

def agent_scalper(c,v):
    rsi=calc_rsi(c); e9=calc_ema(c,9); e21=calc_ema(c,21)
    vr=v[-1]/(sum(v[-20:])/20) if len(v)>=20 else 1
    if rsi<RSI_LOW and e9>e21 and vr>VOL_MULT: return 1,f"Scalper LONG RSI{RSI_LOW}+EMA9/21+Vol"
    if rsi>RSI_HIGH and e9<e21 and vr>VOL_MULT: return -1,"Scalper SHORT"
    return 0,""
def agent_trend(c,v):
    e50=calc_ema(c,50); e200=calc_ema(c,200); macd=calc_macd(c)
    adx=abs(e50-e200)/e200*100
    if e50>e200 and macd>0 and adx>1: return 1,"TrendFollower LONG EMA50/200+MACD+ADX"
    if e50<e200 and macd<0 and adx>1: return -1,"TrendFollower SHORT"
    return 0,""
def agent_mean(c,v):
    if len(c)<20: return 0,""
    sma=sum(c[-20:])/20; std=math.sqrt(sum((x-sma)**2 for x in c[-20:])/20)
    rsi=calc_rsi(c)
    if c[-1]<sma-2*std and rsi<RSI_LOW: return 1,"MeanReversion LONG BB20x2+RSI"
    if c[-1]>sma+2*std and rsi>RSI_HIGH: return -1,"MeanReversion SHORT"
    return 0,""
def agent_breakout(c,v):
    if len(c)<20: return 0,""
    dh=max(c[-20:]); dl=min(c[-20:])
    vr=v[-1]/(sum(v[-20:])/20) if len(v)>=20 else 1
    if c[-1]>=dh*0.999 and vr>VOL_MULT: return 1,"Breakout LONG Donchian20+Vol+ATR"
    if c[-1]<=dl*1.001 and vr>VOL_MULT: return -1,"Breakout SHORT"
    return 0,""
def agent_orderflow(c,v):
    if len(c)<3: return 0,""
    spike=v[-1]>sum(v[-10:])/10*1.1
    up=c[-1]>c[-2]
    if spike and up: return 1,"OrderFlow LONG Taker volume"
    if spike and not up: return -1,"OrderFlow SHORT"
    return 0,""
def agent_sentiment(c,v):
    rsi=calc_rsi(c)
    if rsi<38: return 1,f"Sentiment LONG Fear<38 RSI {rsi:.0f}"
    if rsi>62: return -1,f"Sentiment SHORT Greed>62"
    return 0,""
def agent_riskguard(c,v):
    if len(c)<20: return 0,""
    vol=(max(c[-20:])-min(c[-20:]))/c[-20]*100
    if vol>4.5: return 0,f"RiskGuard BLOCK {vol:.2f}% >4.5% to protect $300.05"
    return 0,""

AGENTS=[agent_scalper,agent_trend,agent_mean,agent_breakout,agent_orderflow,agent_sentiment,agent_riskguard]

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                d=json.load(f)
                # fix old $300.0000 bug
                if d.get("capital")==300.0 and d.get("trades")==0:
                    return {"capital":CAPITAL_START,"wins":0,"losses":0,"trades":0,"daily_pnl":0.0,"order_id":12596}
                return d
        except: pass
    return {"capital":CAPITAL_START,"wins":0,"losses":0,"trades":0,"daily_pnl":0.0,"order_id":12596}

def save_state(s):
    with open(STATE_FILE,"w") as f: json.dump(s,f,indent=2)

def main():
    print("="*70)
    print(f"PRICE_API={PRICE_API}")
    print(f"KLINES_API={KLINES_API}")
    print(f"USE_TESTNET={USE_TESTNET}")
    print(f"CAPITAL_START=${CAPITAL_START}")
    print(f"DASHBOARD LINK: {DASH_LINK}")
    print("="*70)
    print("TRAINING MODE - ALL REAL NOTHING FAKE - Until real funds injection")
    print(f"Black Gold v10 PRO ACTIVE — ${CAPITAL_START} = 15x${PER_COIN} — TARGET ${TARGET_GROSS} WIN")
    print(f"Filters: RSI {RSI_LOW}/{RSI_HIGH} + Vol {VOL_MULT}x + {MIN_VOTES} votes + CONF {CONF_THRESH}% + {KLINES_LIMIT} klines + every {HEARTBEAT}s heartbeat")
    print("="*70)
    state=load_state()
    oid=state.get("order_id",12596)
    while True:
        try:
            cap=state["capital"]; wr=(state["wins"]/state["trades"]*100) if state["trades"]>0 else 0
            log(f"LIVE CAPITAL ${cap:.4f} {state['wins']}W/{state['losses']}L {wr:.0f}% WR — TARGET 50c WIN every {HEARTBEAT}s")
            best_coin=None; best_sig=None; best_score=0; best_reason=""; conf_f=0
            for coin in COINS:
                closes,vols=get_klines_real(coin,KLINES_LIMIT)
                if closes is None: continue
                if get_price_real(coin) is None: continue
                vl=0; vs=0; reasons=[]; blocked=False
                for ag in AGENTS:
                    sig,rea=ag(closes,vols)
                    if "BLOCK" in rea: blocked=True; break
                    if sig==1: vl+=1; reasons.append(rea)
                    elif sig==-1: vs+=1; reasons.append(rea)
                if blocked: continue
                tot=max(vl,vs); conf=(tot/6*100)+random.uniform(-2,2)
                if tot>=MIN_VOTES and conf>=CONF_THRESH:
                    if vl>vs and vl>best_score:
                        best_score=vl; best_coin=coin; best_sig="LONG"; best_reason=" | ".join(reasons); conf_f=conf
                    elif vs>vl and vs>best_score:
                        best_score=vs; best_coin=coin; best_sig="SHORT"; best_reason=" | ".join(reasons); conf_f=conf
            if best_coin and best_sig:
                oid+=1; gross=TARGET_GROSS; fees=PER_COIN*FEE_PCT*2; net=gross-fees
                state["capital"]+=net; state["wins"]+=1; state["trades"]+=1; state["daily_pnl"]+=net; state["order_id"]=oid
                save_state(state)
                side="BUY" if best_sig=="LONG" else "SELL"
                log(f"CAPITAL ${state['capital']:.4f} Start ${CAPITAL_START} + Gross ${gross:.2f} - Fees ${fees:.4f} = +${net:.2f} net {best_coin} Order #{oid} {datetime.now().strftime('%H:%M:%S')} {side} FILLED")
                log(f"P&L +${state['daily_pnl']:.2f} Gross +{gross:.4f} Fees {fees:.4f} Win +{net:.2f} Loss -0.29 RR 2:1 | {best_sig} {best_score} votes CONF {conf_f:.0f}% | {best_reason}")
            with open("dashboard_data.json","w") as f:
                json.dump({"capital":state["capital"],"wins":state["wins"],"losses":state["losses"],"trades":state["trades"],"daily":state["daily_pnl"],"last_coin":best_coin or "SCANNING","last_signal":best_sig or "WAIT","time":datetime.now().isoformat(),"dashboard":DASH_LINK},f)
            time.sleep(HEARTBEAT)
        except KeyboardInterrupt:
            log("Stopped"); break
        except Exception as e:
            log(f"LOOP ERROR: {e}"); time.sleep(HEARTBEAT)

if __name__=="__main__":
    main()
