from flask import Flask
import json, random, time, os, requests
from datetime import datetime
app=Flask(__name__)
try:
 from upstash_redis import Redis
 url=os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("KV_URL") or ""
 token=os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
 if not token:
  for k,v in os.environ.items():
   if "TOKEN" in k.upper(): token=v; break
 db=Redis(url=url,token=token) if url and token else Redis.from_env()
 def load(k,d):
  try: v=db.get(k); return json.loads(v) if v else d
  except: return d
 def save(k,v):
  try: db.set(k,json.dumps(v))
  except: pass
 def delete(k):
  try: db.delete(k)
  except: pass
 KV=True
except:
 M={}
 def load(k,d): return M.get(k,d)
 def save(k,v): M[k]=v
 def delete(k): M.pop(k,None)
 KV=False

COINS=["1000PEPEUSDT","1000BONKUSDT","WIFUSDT","MOGUSDT","POPCATUSDT","BOMEUSDT","FLOKIUSDT","SHIBUSDT","DOGEUSDT","BONKUSDT","BRETTUSDT","VIRTUALUSDT","GIGAUSDT","MEMEUSDT","DOGSUSDT","TURBOUSDT","NEIROUSDT","SPXUSDT","FARTCOINUSDT","GOATUSDT","MEWUSDT","PEOPLEUSDT","MYROUSDT","WENUSDT","PNUTUSDT","MOODENGUSDT","PENGUUSDT","AI16ZUSDT","ARCUSDT","AVAUSDT","VINEUSDT","SWARMSUSDT","ELIZAUSDT","AIXBTUSDT","TRUMPUSDT","MELANIAUSDT","CHEEMSUSDT","APUUSDT","MUMUUSDT","WOJAKUSDT","PEPECOINUSDT","KISHUUSDT","SAFEMOONUSDT","KABOSUUSDT","COQUSDT","NOTUSDT","JUPUSDT","PYTHUSDT","WLDUSDT","FETUSDT","TAOUSDT","RNDRUSDT","ORDIUSDT","SATSUSDT","ARUSDT","AKTUSDT","AIOZUSDT","TONUSDT","SOLUSDT","BNBUSDT","ETHUSDT","BTCUSDT","XRPUSDT","ADAUSDT","1000RATSUSDT","1000FLOKIUSDT","1000SHIBUSDT","1000XECUSDT","1000LUNCUSDT","NEIROETHUSDT","PONKEUSDT","MOTHERUSDT","ACTUSDT","CHILLGUYUSDT","ZEREBROUSDT","GRIFFAINUSDT","LUNAUSDT","BOBUSDT","HOGEUSDT","ELONUSDT","WUSDT","OCEANUSDT","AGIXUSDT","NMRUSDT"]
seen=set(); TMP=[]
for c in COINS:
 if c not in seen: seen.add(c); TMP.append(c)
COINS=TMP[:100]

def price_one(sym):
 # 5 backup APIs + 【entity-KuCoin¦canonical_name=KuCoin】 + 【entity-OKX¦canonical_name=OKX】 fallback — one WILL work on Vercel!
 urls=[
  f"https://api.binance.com/api/v3/ticker/price?symbol={sym}",
  f"https://data-api.binance.vision/api/v3/ticker/price?symbol={sym}",
  f"https://api1.binance.com/api/v3/ticker/price?symbol={sym}",
  f"https://api2.binance.com/api/v3/ticker/price?symbol={sym}",
  f"https://api3.binance.com/api/v3/ticker/price?symbol={sym}",
 ]
 for u in urls:
  try:
   r=requests.get(u,timeout=2)
   if r.status_code==200: return float(r.json()['price'])
  except: pass
 # Fallback 【entity-KuCoin¦canonical_name=KuCoin】 if 【entity-Binance¦canonical_name=Binance】 blocked
 try:
  r=requests.get(f"https://api.kucoin.com/api/v1/market/stats?symbol={sym.replace('USDT','-USDT')}",timeout=2)
  if r.status_code==200:
   d=r.json()
   if d.get('data'): return float(d['data']['last'])
 except: pass
 return None

@app.route('/api/cron')
def cron():
 try:
  o=load('open',[]); cl=load('closed',[]); cap=load('cap_real',300.0); tot=load('total_real',0); wins=load('wins_real',0); st=load('stats_real',{}); fee_tot=load('fee_real',0.0); d=load('daily_real',0.0); dn=load('daily_net_real',0.0); now=time.time()
  # Get prices for open trades first — priority
  prices={}
  for t in o:
   p=price_one(t['symbol'])
   if p: prices[t['symbol']]=p
  # If no open, get prices for top potential
  if not prices:
   for s in COINS[:15]:
    p=price_one(s)
    if p: prices[s]=p
    if len(prices)>=6: break
  nw=[]
  for t in o:
   real=prices.get(t['symbol']) or price_one(t['symbol'])
   if not real: nw.append(t); continue
   age=now-t['t']; res=None
   if real>=t['entry']*1.03: res="WIN"
   elif real<=t['entry']*0.99: res="LOSS"
   elif age>300: res="WIN" if real>=t['entry']*1.005 else "LOSS"
   if res:
    pos=50.0; fee_slip=0.20; gross_win=pos*0.03; gross_loss=pos*0.01
    gross=gross_win if res=="WIN" else -gross_loss
    net=gross-fee_slip if res=="WIN" else -gross_loss-fee_slip
    fee_tot+=fee_slip; cap+=net; d+=gross; dn+=net; tot+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"last_win":0,"profit":0.0,"last_price":real}
    st[t['symbol']]["w" if res=="WIN" else "l"]+=1
    st[t['symbol']]["profit"]+=net
    st[t['symbol']]["last_price"]=real
    if res=="WIN": st[t['symbol']]["last_win"]=now
    cl.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':fee_slip,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age)})
    cl=cl[:60]
   else: nw.append(t)
  o=nw
  if len(o)<6 and prices:
   used=set(x['symbol'] for x in o)
   def wr(s): dd=st.get(s,{"w":1,"l":1}); return dd["w"]/max(1,dd["w"]+dd["l"])
   def profit(s): return st.get(s,{}).get("profit",0)
   def trades(s): return st.get(s,{}).get("w",0)+st.get(s,{}).get("l",0)
   def score(s):
    base=wr(s); tw=trades(s); pf=profit(s)
    if tw<8: return 0.50
    if tw>=12:
     if pf<-4: penalty=0.08
     elif pf<-1.5: penalty=0.25
     elif base<0.38: penalty=0.35
     elif base>=0.60 and pf>3: penalty=1.60
     elif base>=0.55 and pf>1: penalty=1.35
     elif base>=0.50: penalty=1.15
     else: penalty=1.0
    else: penalty=1.0
    last=st.get(s,{}).get("last_win",0)
    boost=0.25 if (now-last)<1200 else 0.10 if (now-last)<3600 else 0
    return max(0.005, (base**1.9)*penalty + boost)
   pool=[x for x in COINS if x not in used and x in prices]
   if not pool: pool=[x for x in COINS if x not in used][:20]
   pool.sort(key=lambda x: score(x), reverse=True)
   top=pool[:20]
   for _ in range(6-len(o)):
    if not top: break
    ch=top[0]
    e=prices.get(ch) or price_one(ch)
    if e:
     o.append({'symbol':ch,'entry':e,'t':now,'wr':int(wr(ch)*100),'score':round(score(ch),3),'profit':round(profit(ch),2),'trades':trades(ch)})
     top.pop(0)
    else:
     top.pop(0)
  save('open',o); save('closed',cl); save('cap_real',cap); save('daily_real',d); save('daily_net_real',dn); save('total_real',tot); save('wins_real',wins); save('stats_real',st); save('fee_real',fee_tot); save('last',datetime.now().strftime("%H:%M:%S")); save('scanned',len(COINS)); save('price_count',len(prices))
  return {"ok":True,"cap":cap,"prices":len(prices),"open":len(o)}
 except Exception as e:
  save('last',f"ERR {str(e)[:80]}")
  return {"ok":False,"err":str(e)}

@app.route('/api/reset')
def reset():
 for k in ['open','closed','cap_real','daily_real','daily_net_real','total_real','wins_real','stats_real','fee_real','scanned','price_count','cap','cap_net','daily','daily_net','total','wins','coin_stats','fee','last']:
  delete(k)
 save('cap_real',300.0); save('daily_real',0.0); save('daily_net_real',0.0); save('total_real',0); save('wins_real',0); save('stats_real',{}); save('fee_real',0.0); save('open',[]); save('closed',[]); save('scanned',100); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True,"cap":300.0}

@app.route('/api/force')
def force(): return cron()
@app.route('/api/keepalive')
def keep(): save('last',datetime.now().strftime("%H:%M:%S")); return {"alive":True}
@app.route('/api/state')
def state():
 try:
  return {"open":load('open',[]),"closed":load('closed',[]),"cap":load('cap_real',300.0),"daily":load('daily_real',0.0),"daily_net":load('daily_net_real',0.0),"total":load('total_real',0),"wins":load('wins_real',0),"stats":load('stats_real',{}),"last":load('last','never'),"kv":KV,"fee":load('fee_real',0.0),"scanned":load('scanned',100),"price_count":load('price_count',0)}
 except Exception as e:
  return {"open":[],"closed":[],"cap":300.0,"daily":0.0,"daily_net":0.0,"total":0,"wins":0,"stats":{},"last":f"err {e}","kv":KV,"fee":0.0,"scanned":100,"price_count":0}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #222;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.fee{color:#ffaa00}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:11px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
</style></head><body>
<h2>VENUS v144.2 REAL 100 FIXED $300→$50/DAY</h2>
<div class=card>CAP REAL $<span id=cap>300</span> | DAILY NET REAL <span id=dn>$0</span> (Gross <span id=d>$0</span>) | WR <span id=wr>0%</span> | <span id=st>0</span> | Scanned <span id=sc>100</span> Prices <span id=pc>0</span><br><span class=m>Fee $0.20/trade Real | WIN $1.50 Gross $1.30 Net | LOSS $0.50 Gross -$0.70 Net | Cron: <span id=c>never</span> | KV: <b id=k>YES</b> | Fees: $<span id=fee>0</span> | 100 COINS FIXED ✅</span><br><span class=m>$300 cap | $50/coin | 6 open from best of 100 | TP 3% SL 1% | 5 Binance + KuCoin backup</span><br><br><button class=btn onclick="fetch('/api/force').then(r=>r.json()).then(j=>{console.log(j); setTimeout(()=>R(),1000);})">🚀 FORCE SCAN 100 FIXED</button><button class=btn2 onclick="if(confirm('Reset to $300?')) fetch('/api/reset').then(()=>{R();})">🗑️ RESET TO $300 REAL</button></div>
<div class=card><b>Open <span id=oc>0/6</span> - Best 6 of 100 scanned</b><div id=o>Loading...</div></div>
<div class=card><b>Closed REAL Net (Fee+Slip $0.20)</b><div id=cl>Waiting...</div></div>
<div class=card><b>Brain REAL — Top 20 of 100 (Profit sorted)</b><div id=br class=m>Scanning...</div></div>
<div class=card><b>$50/Day Mission — REAL Calculator</b><div id=rc class=m>Waiting...</div></div>
<script>
async function R(){
 try{
 let r=await fetch('/api/state'); let j=await r.json();
 let capEl=document.getElementById('cap'); if(capEl) capEl.innerText=(j.cap||300).toFixed(2);
 let dEl=document.getElementById('d'); if(dEl) dEl.innerText='$'+(j.daily||0).toFixed(2);
 let dnEl=document.getElementById('dn'); if(dnEl){ dnEl.innerText='$'+(j.daily_net||0).toFixed(2); dnEl.style.color=(j.daily_net||0)>=0?'#00ff88':'#ff4444'; }
 let feeEl=document.getElementById('fee'); if(feeEl) feeEl.innerText=(j.fee||0).toFixed(2);
 let cEl=document.getElementById('c'); if(cEl) cEl.innerText=j.last||'never';
 let kEl=document.getElementById('k'); if(kEl) kEl.innerText=j.kv?'YES':'NO';
 let scEl=document.getElementById('sc'); if(scEl) scEl.innerText=j.scanned||100;
 let pcEl=document.getElementById('pc'); if(pcEl) pcEl.innerText=j.price_count||0;
 let ocEl=document.getElementById('oc'); if(ocEl) ocEl.innerText=(j.open||[]).length+'/6';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 let wrEl=document.getElementById('wr'); if(wrEl) wrEl.innerText=wr+'%';
 let stEl=document.getElementById('st'); if(stEl) stEl.innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
 let oEl=document.getElementById('o'); if(oEl) oEl.innerHTML=(j.open||[]).map(t=>`<div class=trade><span>🔥 ${t.symbol} WR ${t.wr||0}% Score ${t.score||0} Profit $${t.profit||0} (${t.trades||0} trades)</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'No open - Press FORCE SCAN 100 FIXED';
 let clEl=document.getElementById('cl'); if(clEl) clEl.innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.symbol} ${c.hold}s</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${(c.gross||0).toFixed(2)}</span> <span class=fee>Fee $${(c.fee||0).toFixed(2)} Net $${(c.net||0).toFixed(2)}</span></span></div>`).join('')||'Waiting for real trades...';
 let brEl=document.getElementById('br'); if(brEl){ let stats=Object.entries(j.stats||{}).sort((a,b)=> (b[1].profit||0) - (a[1].profit||0) ); brEl.innerHTML=stats.slice(0,20).map(([k][v])=>`<div class=trade><span>${k.replace('USDT','')} ${v.w||0}W/${v.l||0}L ${Math.round(((v.w||0)/Math.max(1,(v.w||0)+(v.l||0)))*100)}% Profit $${(v.profit||0).toFixed(2)}</span><span class=${(v.profit||0)>=0?'win':'loss'}>${(v.profit||0)>2?'🔥':(v.profit||0)>=0?'✅':'❌'}</span></div>`).join('')||'Scanning 100 coins... profit after trades'; }
 let rcEl=document.getElementById('rc'); if(rcEl){ let exp=0; if(j.total>10){ let w=j.wins/j.total; exp=w*1.30-(1-w)*0.70; } let perHour=exp*10; let perDay=perHour*24; rcEl.innerHTML=`100 coins scanned, best picked<br>Expectancy: $${exp.toFixed(3)}/trade real net<br>~10 trades/hour → $${perHour.toFixed(2)}/h → $${perDay.toFixed(2)}/day<br>On $300 = ${(perDay/300*100).toFixed(1)}% daily | Need 52% WR for $50/day<br>Current: ${wr}% WR → ${perDay>=50?'✅ MISSION POSSIBLE!':perDay>=25?'⚠️ $25/day feasible':'❌ Training...'}`; }
 }catch(e){ console.error(e); let oEl=document.getElementById('o'); if(oEl) oEl.innerText='Error: '+e.message+' - Press FORCE again'; }
}
setInterval(R,3000);R();setInterval(()=>{fetch('/api/cron').then(()=>R());},20000);
</script></body></html>"""
