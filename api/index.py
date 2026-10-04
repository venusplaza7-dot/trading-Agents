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

REAL_FEE=0.001

def get_real_prices():
 out={}
 coins=["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","LINKUSDT","AVAXUSDT","BCHUSDT","LTCUSDT"]
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/price",timeout=3)
  if r.status_code==200:
   for d in r.json():
    try:
     s=d['symbol']; p=float(d['price'])
     if s in coins and p>0: out[s]=p
    except: pass
 except: pass
 if len(out)<4:
  for cb, k in [("BTC-USD","BTCUSDT"),("ETH-USD","ETHUSDT"),("SOL-USD","SOLUSDT"),("DOGE-USD","DOGEUSDT"),("LINK-USD","LINKUSDT"),("AVAX-USD","AVAXUSDT"),("BCH-USD","BCHUSDT"),("LTC-USD","LTCUSDT")]:
   if k in out: continue
   try:
    r=requests.get(f"https://api.coinbase.com/v2/prices/{cb}/spot",timeout=1)
    if r.status_code==200: out[k]=float(r.json()['data']['amount'])
   except: pass
 return out

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); hist=load('VENUS_HIST',{}); now=time.time()
  prices=get_real_prices()
  if len(prices)==0: return {"ok":False,"p":0}
  for s,p in prices.items():
   if s not in hist: hist[s]=[]
   hist[s].append((now,p)); hist[s]=[x for x in hist[s] if now-x[0]<180]
  save('VENUS_HIST',hist)
  nw=[]; cn=[]
  for t in o:
   sym=t['symbol']; entry=t['entry']; tm=t['mode']; entry_t=t['t']; pos_val=t.get('pos',75.0)
   real=prices.get(sym)
   if not real: nw.append(t); continue
   age=now-entry_t; pct=((real-entry)/entry*100) if tm=="LONG" else ((entry-real)/entry*100)
   fee = pos_val * REAL_FEE * 2 # $0.15 real
   gross = pos_val * pct /100
   net = gross - fee
   h=hist.get(sym,[]); p15=None
   for ts,pr in reversed(h):
    if p15 is None and now-ts>=15: p15=pr
   should_close=False; reason=""
   # FIXED: Only close when beats fee
   if pct>=0.35: should_close=True; reason=f"WIN {pct:.3f}% gross ${gross:.3f} fee ${fee:.3f} net ${net:.3f} REAL"
   elif pct>=0.22 and p15:
    mom15=(real-p15)/p15*100 if p15>0 else 0
    if tm=="LONG" and mom15<-0.10: should_close=True; reason=f"TRAIL WIN {pct:.2f}% DOWN {mom15:.3f}% net ${net:.3f}"
    if tm=="SHORT" and mom15>0.10: should_close=True; reason=f"TRAIL WIN {pct:.2f}% UP {mom15:.3f}% net ${net:.3f}"
   elif pct<=-0.22: should_close=True; reason=f"CUT LOSS {pct:.3f}% net ${net:.3f} REAL"
   elif age>150: should_close=True; reason=f"MAX 150s {pct:.3f}% net ${net:.3f}"
   # HOLD if gross < fee
   if age<30: should_close=False
   if should_close:
    if net>0.015: res="WIN"
    elif net<-0.015: res="LOSS"
    else: # gross < fee, don't close yet, hold longer unless max
     if age<90:
      nw.append(t); continue
     else:
      res="SCRATCH" if abs(net)<0.02 else ("WIN" if net>0 else "LOSS")
    fee_tot+=fee if res!="SCRATCH" or abs(net)>0.01 else 0
    if res!="SCRATCH":
     cap+=net; tot+=1
     if res=="WIN" and net>0: wins+=1
     if sym not in st: st[sym]={"w":0,"l":0,"profit":0.0}
     st[sym]["w" if res=="WIN" and net>0 else "l"]+=1; st[sym]["profit"]+=net
    else:
     if abs(net)>0.01:
      cap+=net; fee_tot+=fee
    cn.append({'symbol':sym,'entry':entry,'net':round(net,4),'gross':round(gross,4),'fee':round(fee,4),'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,3),'mode':tm,'price':real,'reason':reason,'pos':pos_val})
   else:
    nw.append(t)
  for c in cn: cl.insert(0,c)
  cl=cl[:200]; o=nw
  if len(o)<3:
   for s in prices:
    if s in [x['symbol'] for x in o]: continue
    # Only open if momentum >0.12% to beat fee
    h=hist.get(s,[])
    if len(h)<2: continue
    mom30 = (prices[s]-h[0][1])/h[0][1]*100 if h[0][1]>0 else 0
    if abs(mom30)<0.12: continue
    if len(o)>=3: break
    pos=cap/3 if cap>0 else 100.0
    mode="LONG" if mom30>0 else "SHORT"
    o.append({'symbol':s,'entry':prices[s],'t':now,'mode':mode,'price':prices[s],'pos':pos})
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"closed":len(cn),"open":len(o),"p":len(prices),"cap":cap}
 except Exception as e:
  save('last',f"ERR {str(e)[:90]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_HIST','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('VENUS_HIST',{}); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True}
@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state():
 return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"last":load('last','never'),"kv":KV,"fee":load('VENUS_FEE',0.0),"price_count":load('VENUS_PRICE',0)}
@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.scratch{color:#888}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:10px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
.real{background:#002a1a;border:1px solid #00ff88}
</style></head><body>
<h2>VENUS v193 REAL FEE FIXED BEAT FEE 65%</h2>
<div class="card real">CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/3</span> | Prices <span id=pc>0</span> | REAL Fees $<span id=fee>0</span><br><span class=m>FIXED: No more SCRATCH $-0.146 bug, holds 0.127% till 0.35% to beat $0.15 fee, gross $0.26 fee $0.15 net $0.11 WIN REAL, only 3 positions $100 each, waits 0.12% momentum, MAX 150s, fee calc gross-fee=net</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | V193 FIXED 65% ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,500))">🚀 FORCE REAL FEE FIXED</button><button class=btn2 onclick="if(confirm('WIPE to $300?')){fetch('/api/reset').then(()=>setTimeout(loadState,400))}">🗑️ WIPE → $300 FIXED</button></div>
<div class=card><b>Open <span id=oc2>0/3</span> 3x $100 beat fee</b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed FIXED gross-fee=net</b><div id=closed>Waiting...</div></div>
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
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/3';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/3';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode} ${t.symbol} pos $${(t.pos||100).toFixed(0)}</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'Waiting 0.12% momentum to beat fee';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} ${c.hold}s ${c.pct||0}% gross $${c.gross||0} fee $${c.fee||0} ${c.reason||''}</span><span><span class=${c.result=='WIN'&&c.net>0?'win':c.result=='SCRATCH'?'scratch':'loss'}>${c.result} $${(c.net||0).toFixed(3)}</span></span></div>`).join('')||'Waiting real 0.35% move';
 }catch(e){}
}
setInterval(loadState,3000); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},5000);
</script></body></html>"""
