from flask import Flask
import json, time, os, requests
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

def get_prices():
 out={}
 # TOP 30 ALWAYS MOVING COINS FROM YOUR SCREENSHOTS
 always_moving=["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","DOGEUSDT","LINKUSDT","ADAUSDT","AVAXUSDT","SUIUSDT","LTCUSDT","UNIUSDT","NEARUSDT","BCHUSDT","AAVEUSDT","ENAUSDT","ONDOUSDT","WLDUSDT","DOTUSDT","PEPEUSDT","BONKUSDT","SHIBUSDT","FLOKIUSDT","WIFUSDT","BRETTUSDT","TURBOUSDT","MORPHOUSDT","SKYUSDT","ALGOUSDT","ARBUSDT"]
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/price",timeout=2.5)
  if r.status_code==200:
   ap={}
   for d in r.json():
    try: ap[d['symbol']]=float(d['price'])
    except: pass
   for base in always_moving:
    try:
     p=None
     if base in ap: p=ap[base]
     elif ("1000"+base) in ap: p=ap["1000"+base]/1000
     if p and 0.0000008 < p < 100000:
      out[base]=p
    except: pass
 except: pass
 if len(out)<5:
  cb_map={"BTCUSDT":"BTC-USD","ETHUSDT":"ETH-USD","SOLUSDT":"SOL-USD","DOGEUSDT":"DOGE-USD","PEPEUSDT":"PEPE-USD","BONKUSDT":"BONK-USD","SHIBUSDT":"SHIB-USD","FLOKIUSDT":"FLOKI-USD","WIFUSDT":"WIF-USD","AVAXUSDT":"AVAX-USD","LINKUSDT":"LINK-USD","LTCUSDT":"LTC-USD","UNIUSDT":"UNI-USD","NEARUSDT":"NEAR-USD","BCHUSDT":"BCH-USD","AAVEUSDT":"AAVE-USD"}
  for sym,cb in cb_map.items():
   if sym in out: continue
   try:
    r=requests.get(f"https://api.coinbase.com/v2/prices/{cb}/spot",timeout=1.2)
    if r.status_code==200:
     p=float(r.json().get('data',{}).get('amount',0))
     if p>0: out[sym]=p
   except: pass
 return out

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); prev=load('VENUS_PREV',{}); prev2=load('VENUS_PREV2',{}); now=time.time()
  prices=get_prices()
  if len(prices)<2: return {"ok":False,"p":len(prices)}
  mom90={}
  for s,p in prices.items():
   if s in prev2 and prev2[s]>0:
    try: mom90[s]=(p-prev2[s])/prev2[s]*100
    except: mom90[s]=0
   else: mom90[s]=0
  save('VENUS_PREV2',prev); save('VENUS_PREV',prices)
  nw=[]; cn=[]
  for t in o:
   entry=t.get('entry',0); age=now-t.get('t',now); tm=t.get('mode','LONG'); sym=t.get('symbol','')
   real=prices.get(sym)
   if age>40:
    if real and entry>0: pct=((real-entry)/entry*100) if tm=="LONG" else ((entry-real)/entry*100)
    else: pct=0
    if abs(pct)<0.025:
     res="SCRATCH"; net=0.0
    elif pct>=0.05:
     res="WIN"; net=0.12 if pct>=0.12 else 0.06
    elif pct<=-0.05:
     res="LOSS"; net=-0.04
    else:
     res="SCRATCH"; net=0.0
    if res!="SCRATCH":
     fee_tot+=0.02; cap+=net; tot+=1
     if res=="WIN": wins+=1
     if sym not in st: st[sym]={"w":0,"l":0,"profit":0.0}
     st[sym]["w" if res=="WIN" else "l"]+=1; st[sym]["profit"]+=net
    cn.append({'symbol':sym,'entry':entry,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,3),'m90':round(mom90.get(sym,0),3),'mode':tm,'price':real or 0})
    continue
   if not real or entry<=0:
    nw.append(t); continue
   pct=((real-entry)/entry*100) if tm=="LONG" else ((entry-real)/entry*100)
   res=None
   if pct<=-0.04: res="LOSS"
   elif pct>=0.05: res="WIN"
   if res:
    net=0.12 if pct>=0.12 else 0.06 if res=="WIN" else -0.04
    fee_tot+=0.02; cap+=net; tot+=1
    if res=="WIN": wins+=1
    if sym not in st: st[sym]={"w":0,"l":0,"profit":0.0}
    st[sym]["w" if res=="WIN" else "l"]+=1; st[sym]["profit"]+=net
    cn.append({'symbol':sym,'entry':entry,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,3),'m90':round(mom90.get(sym,0),3),'mode':tm,'price':real})
   else: nw.append(t)
  for c in cn: cl.insert(0,c)
  cl=cl[:150]; o=nw
  if len(o)<5:
   pool=[]
   for s in prices.keys():
    if s in [x['symbol'] for x in o]: continue
    m90=mom90.get(s,0)
    if abs(m90)>=0.10 and abs(m90)<=2.5:
     pool.append((s,abs(m90),m90))
   pool.sort(key=lambda x: x[1], reverse=True)
   # ALWAYS MOVING: if no vol, take any top market cap moving coins
   if len(pool)<5-len(o):
    for s in ["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","PEPEUSDT","MORPHOUSDT","SKYUSDT","AVAXUSDT","LINKUSDT","WLDUSDT"]:
     if s in prices and s not in [x['symbol'] for x in o] and s not in [p[0] for p in pool]:
      pool.append((s,0.15,0.15))
   for sym,score,m90 in pool[:5-len(o)]:
    e=prices.get(sym)
    if not e: continue
    mode="LONG" if m90>=0 else "SHORT"
    if m90==0.15: mode="LONG"
    o.append({'symbol':sym,'entry':e,'t':now,'m90':round(m90,3),'mode':mode,'price':e,'score':round(score,3)})
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"closed":len(cn),"open":len(o),"p":len(prices)}
 except Exception as e:
  save('last',f"ERR {str(e)[:90]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_PREV','VENUS_PREV2','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True}
@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state():
 return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"last":load('last','never'),"kv":KV,"fee":load('VENUS_FEE',0.0),"price_count":load('VENUS_PRICE',0)}
@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.scratch{color:#888}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:11px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
</style></head><body>
<h2>VENUS v178 5 COINS ALWAYS MOVING FIX STUCK</h2>
<div class=card>CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/5</span> | Prices <span id=pc>0</span> | Fees $<span id=fee>0</span><br><span class=m>ALWAYS MOVING: BTC ETH SOL DOGE PEPE MORPHO SKY etc from your screenshots, 5 coins at once, vol>=0.10% only, stuck>40s → SCRATCH instantly opens new, LOSS.04% WIN.05%+.12% runner, max 40s no more stuck 1 coin</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | V178 5 COINS ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,500))">🚀 FORCE 5 ALWAYS MOVING</button><button class=btn2 onclick="if(confirm('WIPE to $300?')){fetch('/api/reset').then(()=>setTimeout(loadState,400))}">🗑️ WIPE → $300 5 COINS</button></div>
<div class=card><b>Open <span id=oc2>0/5</span> always moving max 40s</b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed 5 ALWAYS MOVING</b><div id=closed>Waiting...</div></div>
<div class=card><b>65% WR 5 COINS</b><div id=calc class=m>Waiting...</div></div>
<script>
async function loadState(){
 try{
  let r=await fetch('/api/state'); let j=await r.json();
  let el=(id)=>document.getElementById(id);
  if(el('cap')) el('cap').innerText=(j.cap||300).toFixed(2);
  if(el('fee')) el('fee').innerText=(j.fee||0).toFixed(2);
  if(el('cr')) el('cr').innerText=j.last||'never';
  if(el('kv')) el('kv').innerText=j.kv?'YES':'NO';
  if(el('pc')) el('pc').innerText=j.price_count||0;
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/5';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/5';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode} ${t.symbol} 90s ${t.m90||0}%</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s /40s max</span></div>`).join('')||'No open - waiting always moving coins BTC ETH SOL etc >=0.10%';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} ${c.hold}s ${c.pct||0}% 90s ${c.m90||0}%</span><span><span class=${c.result=='WIN'?'win':c.result=='SCRATCH'?'scratch':'loss'}>${c.result} $${(c.net||0).toFixed(2)} ${c.pct||0}%</span></span></div>`).join('')||'No trades';
  if(el('calc')){ let exp=0; if(j.total>5){ let w=j.wins/j.total; exp=w*0.06-(1-w)*0.04; } let perDay=exp*600; el('calc').innerHTML=`5 ALWAYS MOVING: WIN.05%+ LOSS.04%<br>Exp $${exp.toFixed(3)}/trade 600/h → $${perDay.toFixed(2)}/day (5 coins)<br>Current ${wr}% ${wr>=50?'✅ 65% close!':'Waiting always moving - never stuck 1 coin'}<br>At 65%: $${(0.65*0.06-0.35*0.04).toFixed(3)}/trade → $${((0.65*0.06-0.35*0.04)*600).toFixed(2)}/day`;}
 }catch(e){}
}
setInterval(loadState,2500); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},5000);
</script></body></html>"""
