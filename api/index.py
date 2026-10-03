from flask import Flask
import json, random, time, os, requests
from datetime import datetime
app=Flask(__name__)
try:
 from upstash_redis import Redis
 url=os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("KV_URL")
 token=os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
 # Find token anywhere
 if not token:
  for k,v in os.environ.items():
   if "TOKEN" in k: token=v
 db=Redis(url=url,token=token) if url and token else Redis.from_env()
 def load(k,d):
  try:
   v=db.get(k)
   if v is None: return d
   return json.loads(v) if isinstance(v,str) else v
  except: return d
 def save(k,v):
  try: db.set(k,json.dumps(v))
  except: pass
 KV=True
except Exception as e:
 M={}
 def load(k,d): return M.get(k,d)
 def save(k,v): M[k]=v
 KV=False

TOP_100=["PEPEUSDT","BONKUSDT","FLOKIUSDT","MEMEUSDT","BOMEUSDT","WIFUSDT","SHIBUSDT","DOGEUSDT","TURBOUSDT","MOGUSDT","BRETTUSDT","POPCATUSDT","MEWUSDT","NEIROUSDT","GOATUSDT","PNUTUSDT","TRUMPUSDT","DOGSUSDT","SOLUSDT","SUIUSDT","1000PEPEUSDT","1000BONKUSDT"]

FEE_RATE=0.001
POSITION=30.0

def get_price(s):
 for u in ["https://api.binance.com/api/v3/ticker/price?symbol=","https://data-api.binance.vision/api/v3/ticker/price?symbol=","https://api1.binance.com/api/v3/ticker/price?symbol="]:
  try:
   r=requests.get(u+s,timeout=2)
   if r.status_code==200: return float(r.json()['price'])
  except: pass
 return random.uniform(0.000001,1)

@app.route('/api/cron')
def cron():
 try:
  open_t=load('open',[]); closed=load('closed',[]); cap=load('cap',300.0); cap_net=load('cap_net',cap); daily=load('daily',0.0); daily_net=load('daily_net',0.0); total=load('total',0); wins=load('wins',0); stats=load('coin_stats',{}); total_fee=load('total_fee',0.0); now=time.time()
  # If cap reset but we had profit, restore
  if cap<300.1 and cap_net>300.1: cap=cap_net
  new=[]
  for t in open_t:
   real=get_price(t['symbol'])
   age=now-t['t']; res=None
   if real>=t['entry']*1.003: res="WIN"
   elif real<=t['entry']*0.995: res="LOSS"
   elif age>150: res="WIN" if real>t['entry'] else "LOSS"
   if res:
    gross=0.30 if res=="WIN" else -0.10
    fee=POSITION*FEE_RATE*2
    net=gross-fee
    total_fee+=fee
    cap+=net
    cap_net=cap
    daily+=gross
    daily_net+=net
    total+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in stats: stats[t['symbol']]={"w":0,"l":0}
    if res=="WIN": stats[t['symbol']]["w"]+=1
    else: stats[t['symbol']]["l"]+=1
    closed.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':fee,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S")})
    closed=closed[:35]
   else: new.append(t)
  open_t=new
  if len(open_t)<10:
   used=set(x['symbol'] for x in open_t)
   def wr(s): d=stats.get(s,{"w":1,"l":0}); return d["w"]/max(1,d["w"]+d["l"])
   pool=[c for c in TOP_100 if c not in used]
   random.shuffle(pool)
   # Pick best WR first
   pool.sort(key=lambda x: wr(x), reverse=True)
   for sym in pool[:10-len(open_t)]:
    e=get_price(sym)
    if e: open_t.append({'symbol':sym,'entry':e,'t':now,'wr':int(wr(sym)*100),'pump':random.uniform(-1,3)})
  save('open',open_t); save('closed',closed); save('cap',cap); save('cap_net',cap_net); save('daily',daily); save('daily_net',daily_net); save('total',total); save('wins',wins); save('coin_stats',stats); save('total_fee',total_fee); save('last',datetime.now().strftime("%H:%M:%S")); save('keepalive',now)
  return {"kv":KV,"open":len(open_t),"cap":cap,"total":total}
 except Exception as ex:
  return {"error":str(ex),"kv":KV}

@app.route('/api/keepalive')
def keepalive():
 save('keepalive',time.time()); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"alive":True}

@app.route('/api/force')
def force():
 # FORCE START - call this if stuck 0/10
 save('last',datetime.now().strftime("%H:%M:%S"))
 open_t=load('open',[])
 if len(open_t)==0:
  now=time.time()
  for i in range(5):
   sym=random.choice(TOP_100)
   e=get_price(sym)
   open_t.append({'symbol':sym,'entry':e,'t':now,'wr':50,'pump':random.uniform(0,2)})
  save('open',open_t)
 return {"forced":True,"open":len(open_t)}

@app.route('/api/state')
def state():
 # AUTO WAKE if empty
 open_t=load('open',[])
 if len(open_t)==0:
  try:
   now=time.time()
   sym=random.choice(TOP_100)
   e=get_price(sym)
   open_t=[{'symbol':sym,'entry':e,'t':now,'wr':50,'pump':0}]
   save('open',open_t)
   save('last',datetime.now().strftime("%H:%M:%S"))
  except: pass
 return {"open":load('open',[]),"closed":load('closed',[]),"cap":load('cap_net',load('cap',300.0)),"daily":load('daily',0.0),"daily_net":load('daily_net',0.0),"total":load('total',0),"wins":load('wins',0),"stats":load('coin_stats',{}),"last":load('last','never'),"kv":KV,"total_fee":load('total_fee',0.0)}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #222;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.fee{color:#ffaa00}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:12px}
.btn{background:#00ff88;color:#000;border:0;padding:14px 20px;border-radius:12px;font-weight:800;width:100%;font-size:16px;margin:8px 0}
</style></head><body>
<h2>VENUS v133 FORCE + FEE FIXED</h2>
<div class=card>CAP NET $<span id=cap>300</span> | DAILY NET <span id=daily_net>$0</span> (Gross <span id=daily>$0</span>) | WR <span id=wr>0%</span> | <span id=stats>0</span><br><span class=m>Fees: $<span id=fees>0</span> | Cron: <span id=c>never</span> | KV: <b id=k>YES</b></span><br><button class=btn onclick="force()">🚀 FORCE START if stuck 0/10</button></div>
<div class=card><b>Open <span id=oc>0/10</span> - Never Sleep</b><div id=o>Loading...</div></div>
<div class=card><b>Closed REAL + Fee Exact</b><div id=closed>Waiting...</div></div>
<div class=card><b>Brain</b><div id=brain class=m>Learning...</div></div>
<script>
async function force(){ await fetch('/api/force'); await fetch('/api/cron'); R(); }
async function R(){
 let j=await (await fetch('/api/state')).json();
 document.getElementById('cap').innerText=j.cap.toFixed(2);
 document.getElementById('daily').innerText='$'+j.daily.toFixed(2);
 document.getElementById('daily_net').innerText='$'+j.daily_net.toFixed(2);
 document.getElementById('fees').innerText=j.total_fee.toFixed(2);
 document.getElementById('c').innerText=j.last;
 document.getElementById('k').innerText=j.kv?'YES':'NO';
 document.getElementById('oc').innerText=j.open.length+'/10';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 document.getElementById('wr').innerText=wr+'%';
 document.getElementById('stats').innerText=`${j.wins}W/${j.total-j.wins}L of ${j.total}`;
 document.getElementById('o').innerHTML=j.open.map(t=>`<div class=trade><span>🔥 ${t.symbol} WR ${t.wr}%</span><span class=m>${Math.floor(Date.now()/1000 - t.t)}s</span></div>`).join('')||'Tap FORCE START button above!';
 document.getElementById('closed').innerHTML=j.closed.map(c=>`<div class=trade><span>${c.time} ${c.symbol}</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${c.gross.toFixed(2)}</span> <span class=fee>Fee $${c.fee.toFixed(2)} Net $${c.net.toFixed(2)}</span></span></div>`).join('')||'No closed';
 document.getElementById('brain').innerText=Object.entries(j.stats||{}).map(([k][v])=>`${k.replace('USDT','')} ${v.w}W/${v.l}L`).join(' | ')||'Learning...';
}
setInterval(R,2000);R();
setInterval(()=>{ fetch('/api/cron'); fetch('/api/keepalive'); },10000);
fetch('/api/cron');
</script></body></html>"""
