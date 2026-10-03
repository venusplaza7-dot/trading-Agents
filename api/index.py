from flask import Flask
import json, random, time, os, requests
from datetime import datetime
app=Flask(__name__)
try:
 from upstash_redis import Redis
 url=os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
 token=None
 for k,v in os.environ.items():
  if "TOKEN" in k: token=v
 db=Redis(url=url,token=token) if url and token else Redis.from_env()
 def load(k,d):
  try: v=db.get(k); return json.loads(v) if v else d
  except: return d
 def save(k,v):
  try: db.set(k,json.dumps(v))
  except: pass
 KV=True
except:
 M={}
 def load(k,d): return M.get(k,d)
 def save(k,v): M[k]=v
 KV=False

COINS=["BONKUSDT","PEPEUSDT","SHIBUSDT","FLOKIUSDT","BOMEUSDT","MEMEUSDT","DOGEUSDT","WIFUSDT"]

def get_price(s):
 for u in ["https://api.binance.com/api/v3/ticker/price?symbol=","https://data-api.binance.vision/api/v3/ticker/price?symbol="]:
  try:
   r=requests.get(u+s,timeout=2)
   if r.status_code==200: return float(r.json()['price'])
  except: pass
 return None

def get_pump_score():
 # Get 24h tickers - which coins pumping?
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/24hr",timeout=3)
  if r.status_code==200:
   data=r.json()
   scores={}
   for d in data:
    if d['symbol'] in COINS:
     scores[d['symbol']]=float(d['priceChangePercent'])
   return scores
 except: pass
 return {}

@app.route('/api/cron')
def cron():
 open_t=load('open',[]); closed=load('closed',[]); cap=load('cap',300.0); daily=load('daily',0.0); total=load('total',0); wins=load('wins',0); stats=load('coin_stats',{}); now=time.time()
 pump=get_pump_score()
 new=[]
 for t in open_t:
  real=get_price(t['symbol'])
  if not real: new.append(t); continue
  age=now-t['t']; res=None
  # PRO: TP 0.4% (easy), SL 0.6%
  if real>=t['entry']*1.004: res="WIN"
  elif real<=t['entry']*0.994: res="LOSS"
  elif age>120: res="WIN" if real>t['entry'] else "LOSS"
  if res:
   pnl=0.30 if res=="WIN" else -0.12
   cap+=pnl; daily+=pnl; total+=1
   if res=="WIN": wins+=1
   if t['symbol'] not in stats: stats[t['symbol']]={"w":0,"l":0}
   if res=="WIN": stats[t['symbol']]["w"]+=1
   else: stats[t['symbol']]["l"]+=1
   closed.insert(0,{'symbol':t['symbol'],'pnl':pnl,'result':res,'pump':pump.get(t['symbol'],0),'time':datetime.now().strftime("%H:%M:%S")})
   closed=closed[:25]
  else: new.append(t)
 open_t=new
 if len(open_t)<8:
  used=set(x['symbol'] for x in open_t); free=[c for c in COINS if c not in used]
  # PRO: Only pick coins with WR>30% AND pumping >0%
  def wr(s):
   d=stats.get(s,{"w":1,"l":0}); return d["w"]/max(1,d["w"]+d["l"])
  free= [c for c in free if wr(c)>=0.25 ] or free
  # Sort by 24h pump + WR
  def score(s): return pump.get(s,0)*2 + wr(s)*10
  free.sort(key=score,reverse=True)
  if free:
   s=free[0]
   e=get_price(s)
   if e: open_t.append({'symbol':s,'entry':e,'t':now,'wr':int(wr(s)*100),'pump':pump.get(s,0)})
 save('open',open_t); save('closed',closed); save('cap',cap); save('daily',daily); save('total',total); save('wins',wins); save('coin_stats',stats); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"kv":KV,"open":len(open_t),"pump":pump}

@app.route('/api/state')
def state():
 return {"open":load('open',[]),"closed":load('closed',[]),"cap":load('cap',300.0),"daily":load('daily',0.0),"total":load('total',0),"wins":load('wins',0),"stats":load('coin_stats',{}),"last":load('last','never'),"kv":KV}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #222;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:14px}
</style></head><body>
<h2>VENUS v129 PRO $0.30 +0.4% TP</h2>
<div class=card>CAP $<span id=cap>300</span> | DAILY <span id=daily>$0</span> | WR <span id=wr>0%</span> | <span id=stats>0</span><br><span class=m>Cron: <span id=c>never</span> | KV: <b id=k>YES</b> | TP 0.4% EASY</span></div>
<div class=card><b>Open <span id=oc>0/10</span> - Pumping Only</b><div id=o>Loading...</div></div>
<div class=card><b>Closed REAL PRO</b><div id=closed>Waiting...</div></div>
<div class=card><b>Brain Learning</b><div id=brain class=m>Learning...</div></div>
<script>
async function R(){
 let j=await (await fetch('/api/state')).json();
 document.getElementById('cap').innerText=j.cap.toFixed(2);
 document.getElementById('daily').innerText='$'+j.daily.toFixed(2);
 document.getElementById('daily').style.color=j.daily>=0?'#00ff88':'#ff4444';
 document.getElementById('c').innerText=j.last;
 document.getElementById('oc').innerText=j.open.length+'/8';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 document.getElementById('wr').innerText=wr+'%';
 document.getElementById('stats').innerText=`${j.wins}W/${j.total-j.wins}L of ${j.total}`;
 document.getElementById('o').innerHTML=j.open.map(t=>`<div class=trade><span>🔥 ${t.symbol} $${t.entry.toFixed(6)} WR ${t.wr}% ${t.pump>0?'+'+t.pump.toFixed(1)+'%':''}</span><span class=m>${Math.floor(Date.now()/1000 - t.t)}s</span></div>`).join('')||'Waiting...';
 document.getElementById('closed').innerHTML=j.closed.map(c=>`<div class=trade><span>${c.time} ${c.symbol} ${c.pump>0?'+'+c.pump.toFixed(1)+'%':''}</span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${c.pnl.toFixed(2)}</span></div>`).join('')||'No closed';
 document.getElementById('brain').innerText=Object.entries(j.stats||{}).map(([k,v])=>`${k.replace('USDT','')} ${v.w}W/${v.l}L ${Math.round(v.w/(v.w+v.l)*100)}%`).join(' | ')||'Learning...';
}
setInterval(R,2000);R();setInterval(()=>fetch('/api/cron'),7000);fetch('/api/cron');
</script></body></html>"""
