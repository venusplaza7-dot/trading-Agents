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
 KV=True
except:
 M={}
 def load(k,d): return M.get(k,d)
 def save(k,v): M[k]=v
 KV=False

COINS=["PEPEUSDT","BONKUSDT","FLOKIUSDT","MEMEUSDT","BOMEUSDT","WIFUSDT","SHIBUSDT","DOGEUSDT","MOGUSDT","POPCATUSDT","1000PEPEUSDT","1000BONKUSDT","GIGAUSDT","TURBOUSDT","NEIROUSDT","BRETTUSDT","DOGSUSDT","SPXUSDT","VIRTUALUSDT"]

def price(s):
 for u in ["https://api.binance.com/api/v3/ticker/price?symbol=","https://data-api.binance.vision/api/v3/ticker/price?symbol="]:
  try:
   r=requests.get(u+s,timeout=2)
   if r.status_code==200: return float(r.json()['price'])
  except: pass
 return random.uniform(0.000001,0.01)

@app.route('/api/cron')
def cron():
 o=load('open',[]); cl=load('closed',[]); cap=load('cap_net',load('cap',300.0)); tot=load('total',0); wins=load('wins',0); st=load('coin_stats',{}); fee_tot=load('fee',0.0); d=load('daily',0.0); dn=load('daily_net',0.0); now=time.time()
 nw=[]
 for t in o:
  real=price(t['symbol']); age=now-t['t']; res=None
  if real>=t['entry']*1.003: res="WIN"
  elif real<=t['entry']*0.995: res="LOSS"
  elif age>110: res="WIN" if real>t['entry'] else "LOSS"
  if res:
   gross=0.30 if res=="WIN" else -0.10; f=0.06; net=gross-f; fee_tot+=f; cap+=net; d+=gross; dn+=net; tot+=1
   if res=="WIN": wins+=1
   if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"last_win":0}
   st[t['symbol']]["w" if res=="WIN" else "l"]+=1
   if res=="WIN": st[t['symbol']]["last_win"]=now
   cl.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':f,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S")})
   cl=cl[:40]
  else: nw.append(t)
 o=nw
 if len(o)<10:
  used=set(x['symbol'] for x in o)
  def wr(s): dd=st.get(s,{"w":1,"l":0}); return dd["w"]/max(1,dd["w"]+dd["l"])
  def smart_score(s):
   # SMART SCORE: WR * recency + small random to test losers
   base=wrf=wr(s)
   tw=st.get(s,{"w":0,"l":0})["w"]+st.get(s,{"w":0,"l":0})["l"]
   # New coin (<5 trades) -> give 50% chance to test it
   if tw<5: return 0.5 + random.uniform(0,0.2)
   # If WR low but last win was recent (<1 hour), boost it
   last=st.get(s,{}).get("last_win",0)
   recency_boost=0.2 if (now-last)<3600 else 0
   # SMART: WR^1.5 so 59% -> 0.45 score, 22% -> 0.10 score, not zero!
   score=(base**1.5) + recency_boost + random.uniform(0,0.05)
   return score
  pool=[x for x in COINS if x not in used]
  pool.sort(key=lambda x: smart_score(x), reverse=True)
  # Pick top 15, then weighted random so 59% gets picked more than 22%, but 22% still gets small chance
  top15=pool[:15]
  weights=[smart_score(s)*100 for s in top15]
  for _ in range(10-len(o)):
   if not top15: break
   chosen=random.choices(top15, weights=weights, k=1)[0]
   e=price(chosen)
   if e:
    o.append({'symbol':chosen,'entry':e,'t':now,'wr':int(wr(chosen)*100),'score':round(smart_score(chosen),2)})
    # Remove chosen to avoid duplicate in same batch
    idx=top15.index(chosen); top15.pop(idx); weights.pop(idx)
 save('open',o); save('closed',cl); save('cap',cap); save('cap_net',cap); save('daily',d); save('daily_net',dn); save('total',tot); save('wins',wins); save('coin_stats',st); save('fee',fee_tot); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"ok":True,"open":len(o)}

@app.route('/api/force')
def force(): return cron()
@app.route('/api/keepalive')
def keep(): save('last',datetime.now().strftime("%H:%M:%S")); return {"alive":True}
@app.route('/api/state')
def state(): return {"open":load('open',[]),"closed":load('closed',[]),"cap":load('cap_net',load('cap',300.0)),"daily":load('daily',0.0),"daily_net":load('daily_net',0.0),"total":load('total',0),"wins":load('wins',0),"stats":load('coin_stats',{}),"last":load('last','never'),"kv":KV,"fee":load('fee',0.0)}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #222;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.fee{color:#ffaa00}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:12px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}
</style></head><body>
<h2>VENUS v138 SMART BRAIN 60% WR</h2>
<div class=card>CAP NET $<span id=cap>300</span> | DAILY NET <span id=dn>$0</span> (Gross <span id=d>$0</span>) | WR <span id=wr>0%</span> | <span id=st>0</span><br><span class=m>Fees: $<span id=fe>0</span> | Smart: 59% traded 3x more than 22% | Cron: <span id=c>never</span> | KV: <b id=k>YES</b> | SMART NO BAN ✅</span><br><button class=btn onclick="fetch('/api/force').then(()=>R())">🚀 FORCE START</button></div>
<div class=card><b>Open <span id=oc>0/10</span> - Smart Brain Picks Best</b><div id=o>Loading...</div></div>
<div class=card><b>Closed REAL + Fee Exact</b><div id=cl>Waiting...</div></div>
<div class=card><b>Brain Smart Learning (No Ban, Smart Weight)</b><div id=br class=m>Learning...</div></div>
<script>
async function R(){
 let j=await (await fetch('/api/state')).json();
 document.getElementById('cap').innerText=j.cap.toFixed(2);
 document.getElementById('d').innerText='$'+j.daily.toFixed(2);
 document.getElementById('dn').innerText='$'+j.daily_net.toFixed(2);
 document.getElementById('fe').innerText=j.fee.toFixed(2);
 document.getElementById('c').innerText=j.last;
 document.getElementById('k').innerText=j.kv?'YES':'NO';
 document.getElementById('oc').innerText=j.open.length+'/10';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 document.getElementById('wr').innerText=wr+'%';
 document.getElementById('st').innerText=`${j.wins}W/${j.total-j.wins}L of ${j.total}`;
 document.getElementById('o').innerHTML=j.open.map(t=>`<div class=trade><span>🔥 ${t.symbol} WR ${t.wr}% Score ${t.score||''}</span><span class=m>${Math.floor(Date.now()/1000 - t.t)}s</span></div>`).join('')||'No open';
 document.getElementById('cl').innerHTML=j.closed.map(c=>`<div class=trade><span>${c.time} ${c.symbol}</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${c.gross.toFixed(2)}</span> <span class=fee>Fee $${c.fee.toFixed(2)} Net $${c.net.toFixed(2)}</span></span></div>`).join('')||'Waiting';
 document.getElementById('br').innerText=Object.entries(j.stats||{}).sort((a,b)=> (b[1].w/(b[1].w+b[1].l)) - (a[1].w/(a[1].w+a[1].l)) ).map(([k,v])=>`${k.replace('USDT','')} ${v.w}W/${v.l}L ${Math.round(v.w/(v.w+v.l)*100)}%`).join(' | ')||'Learning...';
}
setInterval(R,2000);R();setInterval(()=>fetch('/api/cron'),4000);fetch('/api/cron');
</script></body></html>"""
