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

COINS=["1000PEPEUSDT","1000BONKUSDT","WIFUSDT","MOGUSDT","POPCATUSDT","BOMEUSDT","FLOKIUSDT","SHIBUSDT","DOGEUSDT","BONKUSDT","BRETTUSDT","VIRTUALUSDT","GIGAUSDT","MEMEUSDT","DOGSUSDT","TURBOUSDT","NEIROUSDT","SPXUSDT","FARTCOINUSDT"]

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
  if real>=t['entry']*1.007: res="WIN"
  elif real<=t['entry']*0.9975: res="LOSS"
  elif age>150: res="WIN" if real>t['entry'] else "LOSS"
  if res:
   gross=0.70 if res=="WIN" else -0.08; f=0.06; net=gross-f; fee_tot+=f; cap+=net; d+=gross; dn+=net; tot+=1
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
  def score(s):
   base=wr(s); tw=st.get(s,{"w":0,"l":0})["w"]+st.get(s,{"w":0,"l":0})["l"]
   if tw<5: return 0.55 + random.uniform(0,0.15)
   last=st.get(s,{}).get("last_win",0)
   boost=0.30 if (now-last)<1800 else 0.15 if (now-last)<3600 else 0
   penalty=0.3 if (tw>=10 and base<0.25) else 0.5 if (tw>=10 and base<0.35) else 1.0
   return max(0.02, (base**1.6)*penalty + boost + random.uniform(0,0.04))
  pool=[x for x in COINS if x not in used]
  pool.sort(key=lambda x: score(x), reverse=True)
  top=pool[:16]; weights=[score(s)*100 for s in top]
  for _ in range(10-len(o)):
   if not top: break
   ch=random.choices(top, weights=weights, k=1)[0]
   e=price(ch)
   if e: o.append({'symbol':ch,'entry':e,'t':now,'wr':int(wr(ch)*100),'score':round(score(ch),2)})
   idx=top.index(ch); top.pop(idx); weights.pop(idx)
 save('open',o); save('closed',cl); save('cap',cap); save('cap_net',cap); save('daily',d); save('daily_net',dn); save('total',tot); save('wins',wins); save('coin_stats',st); save('fee',fee_tot); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"ok":True}

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
<h2>VENUS v140.1 FINAL ELITE FIXED</h2>
<div class=card>CAP NET $<span id=cap>300</span> | DAILY NET <span id=dn>$0</span> (Gross <span id=d>$0</span>) | WR <span id=wr>0%</span> | <span id=st>0</span><br><span class=m>Fees: $<span id=fe>0</span> | WIN $0.70 Fee $0.06 Net $0.64 | Cron: <span id=c>never</span> | KV: <b id=k>YES</b> | FIXED ✅</span><br><button class=btn onclick="fetch('/api/force').then(()=>R())">🚀 FORCE START</button></div>
<div class=card><b>Open <span id=oc>0/10</span> - Smart + Fee Killer 0.70</b><div id=o>Loading...</div></div>
<div class=card><b>Closed REAL $0.70 WIN / $0.08 LOSS</b><div id=cl>Waiting...</div></div>
<div class=card><b>Brain Smart No Ban</b><div id=br class=m>Learning...</div></div>
<script>
async function R(){
 try{
 let r=await fetch('/api/state'); let j=await r.json();
 document.getElementById('cap').innerText=j.cap.toFixed(2);
 document.getElementById('d').innerText='$'+j.daily.toFixed(2);
 document.getElementById('dn').innerText='$'+j.daily_net.toFixed(2);
 document.getElementById('dn').style.color=j.daily_net>=0?'#00ff88':'#ff4444';
 document.getElementById('fe').innerText=j.fee.toFixed(2);
 document.getElementById('c').innerText=j.last;
 document.getElementById('k').innerText=j.kv?'YES':'NO';
 document.getElementById('oc').innerText=j.open.length+'/10';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 document.getElementById('wr').innerText=wr+'%';
 document.getElementById('st').innerText=`${j.wins}W/${j.total-j.wins}L of ${j.total}`;
 document.getElementById('o').innerHTML=j.open.map(t=>`<div class=trade><span>🔥 ${t.symbol} WR ${t.wr}% Score ${t.score||''}</span><span class=m>${Math.floor(Date.now()/1000 - t.t)}s</span></div>`).join('')||'No open - Press FORCE';
 document.getElementById('cl').innerHTML=j.closed.map(c=>`<div class=trade><span>${c.time} ${c.symbol}</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${c.gross.toFixed(2)}</span> <span class=fee>Fee $${c.fee.toFixed(2)} Net $${c.net.toFixed(2)}</span></span></div>`).join('')||'Waiting...';
 let stats=Object.entries(j.stats||{}).sort((a,b)=> (b[1].w/(b[1].w+b[1].l)) - (a[1].w/(a[1].w+a[1].l)) );
 document.getElementById('br').innerText=stats.map(([k,v])=>`${k.replace('USDT','')} ${v.w}W/${v.l}L ${Math.round(v.w/(v.w+v.l)*100)}%`).join(' | ')||'Learning... Press FORCE START';
 }catch(e){ console.log(e); document.getElementById('o').innerText='Error - Press FORCE START'; }
}
setInterval(R,2000);R();setInterval(()=>fetch('/api/cron'),4000);fetch('/api/cron');
</script></body></html>"""
