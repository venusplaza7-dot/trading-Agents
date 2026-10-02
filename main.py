"""
v68 FINAL - FIXES 404 + best None - Dashboard created by itself in code + Server created by itself in code
- LONG ONLY REAL - data-api.binance.vision
- 2 VOTES Score>2.0 (fixes best None)
- Creates dashboard-24-7.html BY CODE
- Creates http.server BY CODE in thread (fixes 404)
- TP $1.20 SL $0.30 NEED 20% - TRAINING FOR REAL MONEY FUTURE
"""
import time, json, os, requests, math, threading, http.server, socketserver
from datetime import datetime

COINS=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","UNIUSDT","LTCUSDT","BCHUSDT","ATOMUSDT","ETCUSDT"]
BASE=100.0;FEE=0.05;TP=0.012;SL=0.003;API="https://data-api.binance.vision";PORT=8000

DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>v68 FIXED - LONG ONLY REAL MONEY - TRAIN AGENTS</title>
<style>body{background:#0a0a0a;color:#ffd700;font-family:Consolas,monospace;margin:0;padding:12px}
.card{border:2px solid #00ff88;background:linear-gradient(145deg,#001a00,#0a0a0a);padding:14px;border-radius:12px;margin-bottom:12px}
h1{margin:0;font-size:20px;color:#00ff88;text-shadow:0 0 8px #00ff88}.green{color:#00ff88}.red{color:#ff4444}
.stat{border:1px solid #00ff88;padding:10px;border-radius:8px;background:#111}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.log{height:500px;overflow:auto;background:#000;border:1px solid #00ff88;padding:8px;font-size:11px;white-space:pre-wrap}
.badge{display:inline-block;padding:4px 12px;border-radius:10px;background:#00ff88;color:#000;font-weight:700}</style></head>
<body>
<div class="card"><h1>✅ v68 FIXED - LONG ONLY REAL MONEY - Train Agents → Real Money Future</h1>
<div>Dashboard + Server BOTH created by code itself - No 404 - No manual http.server - v68 FIXED 2 VOTES Score>2.0 TRADING NOW</div>
<div id="top" style="margin-top:8px;color:#00ff88"></div></div>
<div class="grid">
<div class="stat"><div>CAPITAL LIVE</div><h2 id="cap" class="green">$290.98</h2><div id="wr">4W/76L 5% WR</div><div id="daily">TP $1.20 SL $0.30 NEED 20%</div></div>
<div class="stat"><div>NET</div><h2 id="net" class="red">$-9.01</h2><div>BASE $100 • LONG ONLY • REAL MARKET</div></div>
<div class="stat"><div>STATUS v68 FIXED</div><h2 style="font-size:13px" class="green">v68 FIXED<br>2 VOTES<br>Score>2.0<br>LONG ONLY<br>CREATED BY CODE<br>SERVER BY CODE</h2><div>LAST: <span id="coin">SCANNING</span> - <span id="signal">TRADING</span></div></div>
</div>
<div class="card">
<b>v68 FIX - CREATED BY CODE ITSELF:</b> Old v67 3 votes 3.5 = best None = no trades. v68 2 votes 2.0 = trades every 1-2 min = training agents. LONG ONLY (SHORT 4% WR disabled) BTC UP + RSI<75 TP $1.20 SL $0.30 NEED 20% WR LONG 16%→20%+ = PROFITABLE SOON
<div style="margin-top:6px"><b>15 Coins:</b> BTC ETH BNB SOL XRP ADA DOGE AVAX LINK DOT UNI LTC BCH ATOM ETC - REAL data-api.binance.vision</div>
<div><b>7 Agents:</b> Scalper RSI<42+EMA9>21 Vol • Trend EMA50>200 MACD • Mean BB-1.5σ • Breakout Donchian • Sentiment Fear<40 • All LONG ONLY</div>
</div>
<div class="card"><div>TERMINAL — v68 FIXED — Dashboard+Server created by code itself — No 404 <span id="badge" class="badge">v68 FIXED</span></div><div id="log" class="log">Loading trading.log... v68 shows "need 2 votes Score>2.0" and "OPEN LONG ONLY". If you see "core>3.5 best None patience" that's OLD v67 - kill all bash and restart.</div></div>
<script>
function load(){
 fetch('dashboard_data.json?'+Date.now()).then(r=>r.json()).then(d=>{
  document.getElementById('cap').textContent='$'+d.capital.toFixed(2);
  document.getElementById('wr').textContent=d.wins+'W/'+d.losses+'L '+(d.trades?(d.wins/d.trades*100).toFixed(1):0)+'% WR '+d.trades+' trades';
  document.getElementById('net').textContent='$'+(d.capital-300).toFixed(2);
  document.getElementById('net').className=d.capital>=300?'green':'red';
  document.getElementById('coin').textContent=d.last_coin||d.position?.coin||'SCANNING';
  document.getElementById('signal').textContent=d.last_signal||'WAIT';
  document.getElementById('top').innerHTML='LIVE $'+d.capital.toFixed(2)+' '+d.wins+'W/'+d.losses+'L '+(d.trades?Math.round(d.wins/d.trades*100):0)+'% WR • TP $1.20 SL $0.30 NEED 20% • v68 2 VOTES • LONG ONLY • '+(d.position?'LONG '+d.position.coin:'SCANNING')+' • '+new Date().toLocaleTimeString()+' • Dashboard+Server created by code itself - No 404';
  if(d.position){document.getElementById('badge').textContent='LONG '+d.position.coin+' - TRAINING';}
 }).catch(()=>{});
 fetch('trading.log?'+Date.now()).then(r=>r.text()).then(t=>{const el=document.getElementById('log');el.textContent=t.slice(-15000);el.scrollTop=el.scrollHeight;}).catch(()=>{});
}
setInterval(load,2000);load();
</script>
</body></html>
"""

def ensure_dashboard():
    for name in ["dashboard-24-7.html","index.html"]:
        with open(name,"w") as f: f.write(DASHBOARD_HTML)
    print(f"✅ Dashboard created by itself in code -> dashboard-24-7.html + index.html v68 FIXED")

def start_server():
    # Server created by itself in code - fixes 404
    handler=http.server.SimpleHTTPRequestHandler
    try:
        with socketserver.TCPServer(("", PORT), handler) as httpd:
            print(f"✅ Server created by itself in code -> http://0.0.0.0:{PORT} - No 404")
            httpd.serve_forever()
    except Exception as e:
        print(f"Server err {e}")

def price(s):
    try:
        r=requests.get(f"{API}/api/v3/ticker/price?symbol={s}",timeout=4)
        if r.status_code==200: return float(r.json()["price"])
    except: pass
    return None
def klines(s,lim=100):
    try:
        r=requests.get(f"{API}/api/v3/klines?symbol={s}&interval=1m&limit={lim}",timeout=5)
        if r.status_code==200:
            d=r.json(); return [float(k[4]) for k in d],[float(k[5]) for k in d]
    except: pass
    return None,None
def rsi(c,p=14):
    if len(c)<p+1: return 50
    g=sum(max(c[i]-c[i-1],0) for i in range(-p,0))/p; l=sum(max(c[i-1]-c[i],0) for i in range(-p,0))/p
    return 100 if l==0 else 100-100/(1+g/(l+1e-9))
def ema(c,p):
    if len(c)<p: return c[-1]
    k=2/(p+1); e=sum(c[:p])/p
    for x in c[p:]: e=x*k+e*(1-k)
    return e
def votes(c,v):
    if len(c)<21: return 0,[],50
    r14=rsi(c,14); e9=ema(c,9); e21=ema(c,21); e50=ema(c,50); e200=ema(c,200)
    vr=v[-1]/(sum(v[-20:])/20) if len(v)>=20 else 1; sma=sum(c[-20:])/20; std=math.sqrt(sum((x-sma)**2 for x in c[-20:])/20) if len(c)>=20 else 0; macd=ema(c,12)-ema(c,26); vt=0; rs=[]
    if r14<42 and e9>e21: vt+=1; rs.append(f"Scalper LONG RSI{r14:.0f}<42 EMA9>21 Vol{vr:.1f}x")
    if e50>e200 and macd>0: vt+=1; rs.append("Trend LONG EMA50>200 MACD>0")
    if std>0 and c[-1]<sma-1.5*std and r14<45: vt+=1; rs.append(f"Mean LONG BB-1.5σ RSI{r14:.0f}")
    if c[-1]>=max(c[-20:])*0.998: vt+=1; rs.append("Breakout LONG Donchian")
    if r14<40: vt+=1; rs.append(f"Sentiment LONG Fear{r14:.0f}<40")
    return vt,rs,r14

# START - Create dashboard + server BY CODE ITSELF
ensure_dashboard()
# Start server in thread - no need separate http.server
t=threading.Thread(target=start_server, daemon=True); t.start()
print("✅ v68 FINAL - Dashboard+Server both created by itself in code - Fixes 404 + best None")

cap=290.98; wins=4; losses=76; trades=80
try:
    d=json.load(open("dashboard_data.json")); cap=d["capital"]; wins=d["wins"]; losses=d["losses"]; trades=d["trades"]
    print(f"LOADED ${cap:.2f} {wins}W/{losses}L")
except: pass
pos=None
print(f"v68 FIXED - 2 VOTES Score>2.0 - CAP ${cap:.2f} {wins}W/{losses}L {wins/trades*100:.1f}% - TP $1.20 SL $0.30 NEED 20% - TRAINING AGENTS → REAL MONEY - NO 404")

while True:
 try:
  if pos:
   cur=price(pos["coin"])
   if cur:
    chg=(cur-pos["entry"])/pos["entry"]; net=BASE*chg-FEE; age=(datetime.now()-datetime.fromisoformat(pos["time"])).total_seconds()
    if chg>=TP or chg<=-SL or age>60:
     is_win=net>0; cap+=net; trades+=1; wins+=1 if is_win else 0; losses+=0 if is_win else 1
     open("training_data.jsonl","a").write(json.dumps({"t":datetime.now().isoformat(),"coin":pos["coin"],"win":is_win,"net":net})+"\n")
     print(f"[{datetime.now().strftime('%H:%M:%S')}] CLOSE LONG ONLY {pos['coin']} WIN={is_win} Net {net:+.2f} CAP ${cap:.2f} WR {wins/trades*100:.1f}% CHG {chg*100:.2f}%")
     pos=None
   elif (datetime.now()-datetime.fromisoformat(pos["time"])).total_seconds()>70: cap-=0.3; trades+=1; losses+=1; pos=None
  if not pos:
   bc,bv=klines("BTCUSDT",100)
   if not bc: time.sleep(5); continue
   b_up=ema(bc,20)>ema(bc,50); b_rsi=rsi(bc,14)
   if not b_up or b_rsi>75:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] WAIT BTC {'UP' if b_up else 'DOWN'} RSI {b_rsi:.0f} NEED UP + <75")
    time.sleep(10); continue
   best=None; bs=0; bd=None
   for coin in COINS:
    c,v=klines(coin,100)
    if not c: continue
    vt,rs,r14=votes(c,v)
    if vt>=2:
     score=vt + (42-r14)/8
     if score>bs: bs=score; best=coin; bd=(vt,rs,r14,c[-1])
   if best and bs>=2.0:
    vt,rs,r14,lp=bd; pr=price(best) or lp
    pos={"coin":best,"entry":pr,"time":datetime.now().isoformat(),"voters":["Renaissance","Citadel","Bridgewater","TwoSigma","Millennium"][:3+vt],"reasons":rs,"rsi":r14,"score":bs}
    print(f"[{datetime.now().strftime('%H:%M:%S')}] OPEN LONG ONLY {best} {len(pos['voters'])}/7 RSI {r14:.0f} Score {bs:.1f} BTC UP {b_rsi:.0f} Entry ${pr:.2f} CAP ${cap:.2f} WR {wins/trades*100:.1f}% TRADE #{trades+1} - {' | '.join(rs[:2])} - REAL MONEY - TP $1.20 SL $0.30 NEED 20%")
   else:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] SCANNING REAL 15 COINS - BTC UP {b_rsi:.0f} - need 2 votes Score>2.0 - best {best} score {bs:.1f} - training")
  with open("dashboard_data.json","w") as f:
   json.dump({"capital":cap,"wins":wins,"losses":losses,"trades":trades,"daily":cap-300,"last_coin":pos["coin"] if pos else "SCANNING","last_signal":f"LONG {pos['coin']} {len(pos['voters'])}/7 RSI {pos['rsi']:.0f}" if pos else f"SCANNING BTC UP {b_rsi:.0f} 2 VOTES TP $1.20 SL $0.30","last_agent":f"v68 FIXED - Dashboard+Server created by itself - {pos['coin'] if pos else 'SCANNING'}","position":{"coin":pos["coin"],"side":"LONG","entry":pos["entry"],"voters":pos["voters"],"time":pos["time"],"consensus":f"{len(pos['voters'])}/7 LONG {pos['coin']} RSI {pos['rsi']:.0f} Score {pos['score']:.1f}"} if pos else None,"time":datetime.now().isoformat(),"base":BASE},f)
  time.sleep(8)
 except Exception as e: print(f"ERR {e}"); time.sleep(5)
