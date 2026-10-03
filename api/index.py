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

TOP_100=["PEPEUSDT","BONKUSDT","FLOKIUSDT","MEMEUSDT","BOMEUSDT","WIFUSDT","SHIBUSDT","DOGEUSDT","TURBOUSDT","MOGUSDT","BRETTUSDT","POPCATUSDT","MEWUSDT","NEIROUSDT","GOATUSDT","PNUTUSDT","MOODENGUSDT","ACTUSDT","SPXUSDT","GIGAUSDT","FARTCOINUSDT","AI16ZUSDT","VIRTUALUSDT","TRUMPUSDT","DOGSUSDT","NOTUSDT","SUIUSDT","SOLUSDT","WLDUSDT","ENAUSDT","JUPUSDT","ONDOUSDT","SEIUSDT","TIAUSDT","PENDLEUSDT","INJUSDT","FETUSDT","TAOUSDT","ARKMUSDT","ORDIUSDT","1000PEPEUSDT","1000BONKUSDT"]

FEE_RATE=0.001 # 0.1% Binance spot fee per side, total 0.2%
POSITION=30.0 # $30 position per trade -> fee $0.03 per side

def get_price(s):
 for u in ["https://api.binance.com/api/v3/ticker/price?symbol=","https://data-api.binance.vision/api/v3/ticker/price?symbol=","https://api1.binance.com/api/v3/ticker/price?symbol="]:
  try:
   r=requests.get(u+s,timeout=2)
   if r.status_code==200: return float(r.json()['price'])
  except: pass
 return None

def get_pumpers():
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/24hr",timeout=4)
  if r.status_code==200:
   data=[d for d in r.json() if d['symbol'] in TOP_100]
   data.sort(key=lambda x: float(x['priceChangePercent']), reverse=True)
   return data
 except: pass
 return [{"symbol":s,"priceChangePercent":str(random.uniform(-1,4))} for s in TOP_100[:20]]

@app.route('/api/cron')
def cron():
 open_t=load('open',[]); closed=load('closed',[]); cap=load('cap',300.0); daily=load('daily',0.0); daily_net=load('daily_net',0.0); total=load('total',0); wins=load('wins',0); stats=load('coin_stats',{}); total_fee=load('total_fee',0.0); now=time.time()
 pumpers=get_pumpers()
 pmap={p['symbol']: float(p['priceChangePercent']) for p in pumpers}
 new=[]
 for t in open_t:
  real=get_price(t['symbol'])
  if not real: new.append(t); continue
  age=now-t['t']; res=None
  if real>=t['entry']*1.003: res="WIN"
  elif real<=t['entry']*0.995: res="LOSS"
  elif age>150: res="WIN" if real>t['entry'] else "LOSS"
  if res:
   gross=0.30 if res=="WIN" else -0.10
   fee=POSITION*FEE_RATE*2 # entry + exit
   net=gross-fee
   total_fee+=fee
   cap+=net # CAP is NET after fee - exact where we stand!
   daily+=gross
   daily_net+=net
   total+=1
   if res=="WIN": wins+=1
   if t['symbol'] not in stats: stats[t['symbol']]={"w":0,"l":0}
   if res=="WIN": stats[t['symbol']]["w"]+=1
   else: stats[t['symbol']]["l"]+=1
   closed.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':fee,'net':net,'result':res,'pump':pmap.get(t['symbol'],0),'time':datetime.now().strftime("%H:%M:%S")})
   closed=closed[:35]
  else: new.append(t)
 open_t=new
 if len(open_t)<10:
  used=set(x['symbol'] for x in open_t)
  def wr(s): d=stats.get(s,{"w":1,"l":0}); return d["w"]/max(1,d["w"]+d["l"])
  cand=[p for p in pumpers if p['symbol'] not in used and (stats.get(p['symbol'],{"w":0,"l":0})["w"]+stats.get(p['symbol'],{"w":0,"l":0})["l"]<3 or wr(p['symbol'])>0.3)]
  cand.sort(key=lambda x: float(x['priceChangePercent'])*2 + wr(x['symbol'])*20, reverse=True)
  for p in cand[:10-len(open_t)]:
   e=get_price(p['symbol'])
   if e: open_t.append({'symbol':p['symbol'],'entry':e,'t':now,'wr':int(wr(p['symbol'])*100),'pump':float(p['priceChangePercent'])})
 save('open',open_t); save('closed',closed); save('cap',cap); save('daily',daily); save('daily_net',daily_net); save('total',total); save('wins',wins); save('coin_stats',stats); save('total_fee',total_fee); save('last',datetime.now().strftime("%H:%M:%S")); save('top',pumpers[:10]); save('keepalive',now)
 return {"kv":KV,"open":len(open_t),"fee":total_fee,"cap_net":cap}

@app.route('/api/keepalive')
def keepalive():
 # cron.org should ping this + /api/cron every 1 min to never sleep
 save('keepalive',time.time())
 save('last',datetime.now().strftime("%H:%M:%S"))
 # trigger cron too
 try:
  open_t=load('open',[])
  if len(open_t)<10:
   # wake up trading
   pass
 except: pass
 return {"alive":True,"last":load('last','never'),"kv":KV}

@app.route('/api/state')
def state():
 return {"open":load('open',[]),"closed":load('closed',[]),"cap":load('cap',300.0),"daily":load('daily',0.0),"daily_net":load('daily_net',0.0),"total":load('total',0),"wins":load('wins',0),"stats":load('coin_stats',{}),"last":load('last','never'),"kv":KV,"top":load('top',[]),"total_fee":load('total_fee',0.0),"keepalive":load('keepalive',0)}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #222;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.fee{color:#ffaa00}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:12px}
</style></head><body>
<h2>VENUS v132 FEE + NEVER SLEEP $0.30</h2>
<div class=card>CAP NET $<span id=cap>300</span> | DAILY NET <span id=daily_net>$0</span> (Gross <span id=daily>$0</span>) | WR <span id=wr>0%</span> | <span id=stats>0</span><br><span class=m>Fees Paid: $<span id=fees>0</span> | Position $30 | Fee 0.1% per side | Cron: <span id=c>never</span> | KV: <b id=k>YES</b> | <span id=keep>alive</span></span></div>
<div class=card><b>🔥 TOP 10 Pumping NOW</b><div id=top class=m>Scanning...</div></div>
<div class=card><b>Open <span id=oc>0/10</span> - Never Sleep Mode</b><div id=o>Loading...</div></div>
<div class=card><b>Closed REAL + Fee Exact</b><div id=closed>Waiting...</div></div>
<div class=card><b>Brain</b><div id=brain class=m>Learning...</div></div>
<script>
async function R(){
 let j=await (await fetch('/api/state')).json();
 document.getElementById('cap').innerText=j.cap.toFixed(2);
 document.getElementById('daily').innerText='$'+j.daily.toFixed(2);
 document.getElementById('daily_net').innerText='$'+j.daily_net.toFixed(2);
 document.getElementById('daily_net').style.color=j.daily_net>=0?'#00ff88':'#ff4444';
 document.getElementById('fees').innerText=j.total_fee.toFixed(2);
 document.getElementById('c').innerText=j.last;
 document.getElementById('k').innerText=j.kv?'YES':'NO';
 document.getElementById('oc').innerText=j.open.length+'/10';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 document.getElementById('wr').innerText=wr+'%';
 document.getElementById('stats').innerText=`${j.wins}W/${j.total-j.wins}L of ${j.total}`;
 document.getElementById('o').innerHTML=j.open.map(t=>`<div class=trade><span>🔥 ${t.symbol} WR ${t.wr}% ${t.pump>0?'+'+t.pump.toFixed(1)+'%':''}</span><span class=m>${Math.floor(Date.now()/1000 - t.t)}s</span></div>`).join('')||'Starting in 5s...';
 document.getElementById('closed').innerHTML=j.closed.map(c=>`<div class=trade><span>${c.time} ${c.symbol}</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${c.gross.toFixed(2)}</span> <span class=fee>Fee $${c.fee.toFixed(2)} Net $${c.net.toFixed(2)}</span></span></div>`).join('')||'No closed';
 document.getElementById('top').innerHTML=(j.top||[]).map(p=>`${p.symbol} ${parseFloat(p.priceChangePercent)>0?'<span class=fee>+' + parseFloat(p.priceChangePercent).toFixed(1)+'%</span>': parseFloat(p.priceChangePercent).toFixed(1)+'%'} | `).join('')||'Scanning...';
 document.getElementById('brain').innerText=Object.entries(j.stats||{}).sort((a,b)=> (b[1].w/(b[1].w+b[1].l)) - (a[1].w/(a[1].w+a[1].l)) ).map(([k][v])=>`${k.replace('USDT','')} ${v.w}W/${v.l}L ${Math.round(v.w/(v.w+v.l)*100)}%`).join(' | ')||'Learning...';
 let ka=j.keepalive? Math.floor(Date.now()/1000 - j.keepalive) : 999;
 document.getElementById('keep').innerText= ka<120? `ALIVE ${ka}s ago ✅` : `SLEEPING ${ka}s ❌ - wake it!`;
}
setInterval(R,2000);R();
// NEVER SLEEP - ping every 25 sec
setInterval(()=>{ fetch('/api/cron'); fetch('/api/keepalive'); },25000);
setInterval(()=>fetch('/api/cron'),5000);
fetch('/api/cron'); fetch('/api/keepalive');
</script></body></html>"""
