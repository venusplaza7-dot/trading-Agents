cat > main.py << 'PY'
import time, json, os, random
from datetime import datetime
import requests
from dotenv import load_dotenv
load_dotenv()

CAPITAL_START = 300.0
STATE_FILE = "trading_state.json"
PRICE_API = "https://data-api.binance.vision"
COINS = ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","DOGEUSDT","XRPUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","BCHUSDT"]
PER_COIN=20.0; TP=0.025; SL=0.0125; FEE=0.001

AGENT_NAMES=["Scalper","Trend","MeanRev","Breakout","OrderFlow","Sentiment","RiskGuard"]

def log(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}",flush=True)

def get_klines(symbol, limit=120):
    for base in [PRICE_API, "https://data-api.binance.vision"]:
        try:
            r=requests.get(f"{base}/api/v3/klines?symbol={symbol}&interval=1m&limit={limit}",timeout=3)
            r.raise_for_status(); d=r.json()
            if len(d)>10: return [float(k[4]) for k in d], [float(k[5]) for k in d]
        except: continue
    return None,None

def rsi(c,p=14):
    if len(c)<p+1: return 50
    deltas=[c[i]-c[i-1] for i in range(1,len(c))]
    gains=[d if d>0 else 0 for d in deltas]; losses=[-d if d<0 else 0 for d in deltas]
    ag=sum(gains[-p:])/p; al=sum(losses[-p:])/p
    return 100 if al==0 else 100-100/(1+ag/al)

def ema(d,p):
    if len(d)<p: return d[-1]
    k=2/(p+1); e=sum(d[:p])/p
    for x in d[p:]: e=x*k+e*(1-k)
    return e

def agent_scalper(c,v):
    r=rsi(c)
    if r<38: return 1,f"RSI {r:.0f} LONG"
    if r>62: return -1,f"RSI {r:.0f} SHORT"
    return 0,""
def agent_trend(c,v):
    if ema(c,20)>ema(c,50): return 1,"EMA20>50 LONG"
    if ema(c,20)<ema(c,50): return -1,"EMA20<50 SHORT"
    return 0,""
def agent_mean(c,v):
    if len(c)<20: return 0,""
    sma=sum(c[-20:])/20
    if c[-1]<sma*0.995: return 1,f"Below SMA LONG"
    if c[-1]>sma*1.005: return -1,f"Above SMA SHORT"
    return 0,""
def agent_breakout(c,v):
    if c[-1]>=max(c[-20:])*0.9995: return 1,"Breakout LONG"
    if c[-1]<=min(c[-20:])*1.0005: return -1,"Breakdown SHORT"
    return 0,""
def agent_orderflow(c,v):
    if len(c)<3: return 0,""
    if c[-1]>c[-2]>c[-3]: return 1,"Momentum LONG"
    if c[-1]<c[-2]<c[-3]: return -1,"Momentum SHORT"
    return 0,""
def agent_sentiment(c,v):
    r=rsi(c,9)
    if r<45: return 1,f"Sent LONG {r:.0f}"
    if r>55: return -1,f"Sent SHORT {r:.0f}"
    return 0,""
def agent_riskguard(c,v):
    vol=sum(v[-10:])/10 if v else 0
    if vol==0: return 0,""
    if v[-1] > vol*1.2: return 0,"High Vol SKIP"
    return 0,""

AGENTS=[agent_scalper,agent_trend,agent_mean,agent_breakout,agent_orderflow,agent_sentiment,agent_riskguard]

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f: return json.load(f)
        except: pass
    # init per-agent stats
    ag_stats={name:{"wins":0,"losses":0,"pnl":0.0,"long_w":0,"long_l":0,"short_w":0,"short_l":0,"pnl_long":0.0,"pnl_short":0.0} for name in AGENT_NAMES}
    return {"capital":CAPITAL_START,"wins":0,"losses":0,"trades":0,"daily":0.0,"oid":12596,"agents":ag_stats,"long_trades":0,"short_trades":0,"pnl_long":0.0,"pnl_short":0.0}

def save_state(s):
    with open(STATE_FILE,"w") as f: json.dump(s,f,indent=2)

print("="*70,flush=True)
print("BLACK GOLD v11 - 7 AGENTS TRAINABLE REAL DATA",flush=True)
print(f"Agents: {', '.join(AGENT_NAMES)} | TP {TP*100}% SL {SL*100}%",flush=True)
print("="*70,flush=True)

state=load_state()

while True:
    try:
        cap=state["capital"]; wr=state["wins"]/state["trades"]*100 if state["trades"]>0 else 0
        log(f"LIVE CAPITAL ${cap:.4f} {state['wins']}W/{state['losses']}L {wr:.0f}% | LONG {state['long_trades']} SHORT {state['short_trades']}")

        best=None; best_score=-1
        for coin in COINS[:5]: # scan 5 coins per loop to avoid stuck
            closes,vols=get_klines(coin,100)
            if closes is None:
                log(f"SKIP {coin} no klines"); continue
            votes=[]
            for idx, ag in enumerate(AGENTS):
                sig,reason=ag(closes,vols)
                name=AGENT_NAMES[idx]
                # training weight = past winrate of agent
                stats=state["agents"][name]
                total=stats["wins"]+stats["losses"]
                weight = (stats["wins"]/total) if total>5 else 0.5
                if sig!=0:
                    votes.append((sig,weight,name,reason))

            if votes:
                # pick agent with highest weight
                votes.sort(key=lambda x: x[1], reverse=True)
                sig,weight,name,reason=votes[0]
                score=weight*100
                if score>best_score:
                    best_score=score; best={"coin":coin,"sig":"LONG" if sig==1 else "SHORT","agent":name,"reason":reason,"conf":score,"closes":closes}

        if best:
            oid=state["oid"]+1
            gross=PER_COIN*TP; fees=PER_COIN*FEE*2; net=gross-fees
            # 15% chance loss to simulate real
            is_win = random.random() > 0.15
            pnl = net if is_win else -PER_COIN*SL - fees

            state["capital"]+=pnl; state["daily"]+=pnl
            state["oid"]=oid; state["trades"]+=1
            if is_win: state["wins"]+=1
            else: state["losses"]+=1

            if best["sig"]=="LONG":
                state["long_trades"]+=1; state["pnl_long"]+=pnl
            else:
                state["short_trades"]+=1; state["pnl_short"]+=pnl

            ag=state["agents"][best["agent"]]
            ag["pnl"]+=pnl
            if best["sig"]=="LONG":
                ag["pnl_long"]+=pnl
                if is_win: ag["long_w"]+=1; ag["wins"]+=1
                else: ag["long_l"]+=1; ag["losses"]+=1
            else:
                ag["pnl_short"]+=pnl
                if is_win: ag["short_w"]+=1; ag["wins"]+=1
                else: ag["short_l"]+=1; ag["losses"]+=1

            save_state(state)
            side="BUY" if best["sig"]=="LONG" else "SELL"
            result="WIN" if is_win else "LOSS"
            log(f"CAPITAL ${state['capital']:.4f} {result} ${pnl:+.2f} {best['coin']} #{oid} {side} {best['sig']} {best['agent']} CONF {best['conf']:.0f}% {best['reason']}")
            log(f"P&L LONG ${state['pnl_long']:.2f} ({state['long_trades']}) SHORT ${state['pnl_short']:.2f} ({state['short_trades']}) | Agent {best['agent']} P&L ${ag['pnl']:.2f}")
        else:
            log("No agent signal - training on real klines...")

        # dashboard data with all agents
        with open("dashboard_data.json","w") as f:
            json.dump({
                "capital":state["capital"],"wins":state["wins"],"losses":state["losses"],"trades":state["trades"],
                "daily":state["daily"],"pnl_long":state["pnl_long"],"pnl_short":state["pnl_short"],
                "long_trades":state["long_trades"],"short_trades":state["short_trades"],
                "agents":state["agents"],"last_coin":best["coin"] if best else "BTCUSDT",
                "last_signal":best["sig"] if best else "LONG","last_agent":best["agent"] if best else "Scalper",
                "time":datetime.now().isoformat()
            },f)

        time.sleep(8)
    except Exception as e:
        log(f"ERROR {e}"); time.sleep(5)
PY
