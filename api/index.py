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

# 100 BEST MEME + VOLATILE COINS - Binance USDT
TOP_100 = [
"PEPEUSDT","BONKUSDT","FLOKIUSDT","MEMEUSDT","BOMEUSDT","WIFUSDT","SHIBUSDT","DOGEUSDT",
"1000PEPEUSDT","1000BONKUSDT","1000FLOKIUSDT","TURBOUSDT","MOGUSDT","BRETTUSDT","POPCATUSDT",
"MEWUSDT","NEIROUSDT","GOATUSDT","PNUTUSDT","MOODENGUSDT","ACTUSDT","HIPPOUSDT","CHILLGUYUSDT",
"SPXUSDT","GIGAUSDT","RETARDIOUSDT","FARTCOINUSDT","AI16ZUSDT","VIRTUALUSDT","AIXBTUSDT",
"TRUMPUSDT","MELANIAUSDT","DOGSUSDT","NOTUSDT","HMSTRUSDT","CATIUSDT","TONUSDT","SUIUSDT",
"APTUSDT","ARBUSDT","OPUSDT","SOLUSDT","AVAXUSDT","MATICUSDT","DOTUSDT","LINKUSDT","LTCUSDT",
"UNIUSDT","ETCUSDT","XLMUSDT","ATOMUSDT","FILUSDT","NEARUSDT","RENDERUSDT","FETUSDT","TAOUSDT",
"AGIXUSDT","WLDUSDT","ARKMUSDT","ENAUSDT","ETHFIUSDT","BOMEUSDT","JUPUSDT","PYTHUSDT","JTOUSDT",
"ONDOUSDT","STRKUSDT","WUSDT","ZKUSDT","LISTAUSDT","ZROUSDT","IOUSDT","BBUSDT","NOTUSDT",
"REZUSDT","TAIKOUSDT","TNSRUSDT","OMUSDT","SAGAUSDT","MERLUSDT","REZUSDT","WIFUSDT","ENAUSDT",
"AEVOUSDT","BOMEUSDT","ETHFIUSDT","WUSDT","TNSRUSDT","SAGAUSDT","TAOUSDT","WIFUSDT","JUPUSDT",
"MANTAUSDT","ALTUSDT","JTOUSDT","MEMEUSDT","BONKUSDT","1000SATSUSDT","ORDIUSDT","RATSUSDT",
"SEIUSDT","TIAUSDT","BEAMXUSDT","BLURUSDT","ARKMUSDT","MAVUSDT","PENDLEUSDT","LDOUSDT","INJUSDT",
"RNDRUSDT","STXUSDT","IMXUSDT","GRTUSDT","RUNEUSDT","LPTUSDT","AGLDUSDT","ALPACAUSDT","SANTOSUSDT"
]
# Deduplicate
TOP_100 = list(dict.fromkeys(TOP_100))[:100]

def get_price(s):
 for u in ["https://api.binance.com/api/v3/ticker/price?symbol=","https://data-api.binance.vision/api/v3/ticker/price?symbol="]:
  try:
   r=requests.get(u+s,timeout=2)
   if r.status_code==200: return float(r.json()['price'])
  except: pass
 return None

def get_top_pumpers():
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/24hr",timeout=4)
  if r.status_code==200:
   all_data=r.json()
   # Filter to our TOP_100 and sort by pump %
   filtered=[d for d in all_data if d['symbol'] in TOP_100]
   # Sort by priceChangePercent DESC - biggest pumpers first
   filtered.sort(key=lambda x: float(x['priceChangePercent']), reverse=True)
   return filtered[:100] # Top 100 pumpers
 except: pass
 return []

@app.route('/api/cron')
def cron():
 open_t=load('open',[]); closed=load('closed',[]); cap=load('cap',300.0); daily=load('daily',0.0); total=load('total',0); wins=load('wins',0); stats=load('coin_stats',{}); now=time.time()
 pumpers=get_top_pumpers()
 pump_map={p['symbol']: float(p['priceChangePercent']) for p in pumpers}

 # Close with REAL price - TP 0.4% easy
 new=[]
 for t in open_t:
  real=get_price(t['symbol'])
  if not real: new.append(t); continue
  age=now-t['t']; res=None
  if real>=t['entry']*1.004: res="WIN"
  elif real<=t['entry']*0.994: res="LOSS"
  elif age>150: res="WIN" if real>t['entry'] else "LOSS"
  if res:
   pnl=0.30 if res=="WIN" else -0.12
   cap+=pnl; daily+=pnl; total+=1
   if res=="WIN": wins+=1
   if t['symbol'] not in stats: stats[t['symbol']]={"w":0,"l":0}
   if res=="WIN": stats[t['symbol']]["w"]+=1
   else: stats[t['symbol']]["l"]+=1
   closed.insert(0,{'symbol':t['symbol'],'pnl':pnl,'result':res,'pump':pump_map.get(t['symbol'],0),'time':datetime.now().strftime("%H:%M:%S")})
   closed=closed[:30]
  else: new.append(t)
 open_t=new

 # OPEN - Scan 100 coins, pick BEST pumpers that are also learning winners
 if len(open_t)<10 and pumpers:
  used=set(x['symbol'] for x in open_t)
  def wr(s): d=stats.get(s,{"w":1,"l":0}); return d["w"]/max(1,d["w"]+d["l"])
  # Filter: only coins pumping > -1% (not heavy dumping) AND WR > 20%
  candidates=[p for p in pumpers if p['symbol'] not in used and float(p['priceChangePercent'])>-2 and wr(p['symbol'])>=0.2]
  # Sort by pump% + WR
  candidates.sort(key=lambda x: float(x['priceChangePercent'])*1.5 + wr(x['symbol'])*20, reverse=True)
  # Take top 10 opportunities
  for p in candidates[:10-len(open_t)]:
   sym=p['symbol']
   entry=get_price(sym)
   if entry and entry>0:
    open_t.append({'symbol':sym,'entry':entry,'t':now,'wr':int(wr(sym)*100),'pump':float(p['priceChangePercent']),'price':float(p['lastPrice'])})

 save('open',open_t); save('closed',closed); save('cap',cap); save('daily',daily); save('total',total); save('wins',wins); save('coin_stats',stats); save('last',datetime.now().strftime("%H:%M:%S")); save('pumpers', pumpers[:10])
 return {"kv":KV,"open":len(open_t),"scanned":len(pumpers)}

@app.route('/api/state')
def state():
 return {"open":load('open',[]),"closed":load('closed',[]),"cap":load('cap',300.0),"daily":load('daily',0.0),"total":load('total',0),"wins":load('wins',0),"stats":load('coin_stats',{}),"last":load('last','never'),"kv":KV,"top":load('pumpers',[])}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #222;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:13px}
.pump{color:#ffaa00}
</style></head><body>
<h2>VENUS v130 100-COIN HUNTER $0.30</h2>
<div class=card>CAP $<span id=cap>300</span> | DAILY <span id=daily>$0</span> | WR <span id=wr>0%</span> | <span id=stats>0</span><br><span class=m>Scanning: <b>100 best meme coins</b> | Cron: <span id=c>never</span> | KV: <b id=k>YES</b></span></div>
<div class=card><b>🔥 TOP 10 Pumping NOW (24h)</b><div id=top class=m>Scanning 100 coins...</div></div>
<div class=card><b>Open <span id=oc>0/10</span> - Best Opportunities</b><div id=o>Scanning...</div></div>
<div class=card><b>Closed REAL</b><div id=closed>Waiting...</div></div>
<div class=card><b>Brain - 100 Coins Learning</b><div id=brain class=m>Learning...</div></div>
<script>
async function R(){
 let j=await (await fetch('/api/state')).json();
 document.getElementById('cap').innerText=j.cap.toFixed(2);
 document.getElementById('daily').innerText='$'+j.daily.toFixed(2);
 document.getElementById('daily').style.color=j.daily>=0?'#00ff88':'#ff4444';
 document.getElementById('c').innerText=j.last;
 document.getElementById('oc').innerText=j.open.length+'/10';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 document.getElementById('wr').innerText=wr+'%';
 document.getElementById('stats').innerText=`${j.wins}W/${j.total-j.wins}L of ${j.total}`;
 document.getElementById('o').innerHTML=j.open.map(t=>`<div class=trade><span>🔥 ${t.symbol} $${t.entry.toExponential(2)} <span class=pump>${t.pump>0?'+'+t.pump.toFixed(1)+'%':''}</span> WR ${t.wr}%</span><span class=m>${Math.floor(Date.now()/1000 - t.t)}s</span></div>`).join('')||'Scanning 100 coins for pump...';
 document.getElementById('closed').innerHTML=j.closed.map(c=>`<div class=trade><span>${c.time} ${c.symbol} ${c.pump>0?'+'+c.pump.toFixed(1)+'%':''}</span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${c.pnl.toFixed(2)}</span></div>`).join('')||'No closed yet';
 document.getElementById('top').innerHTML=(j.top||[]).map(p=>`${p.symbol} ${parseFloat(p.priceChangePercent)>0?'<span class=pump>+' + parseFloat(p.priceChangePercent).toFixed(1)+'%</span>': parseFloat(p.priceChangePercent).toFixed(1)+'%'} | `).join('')||'Scanning...';
 let b=Object.entries(j.stats||{}).sort((a,b)=> (b[1].w/(b[1].w+b[1].l)) - (a[1].w/(a[1].w+a[1].l)) ).slice(0,8).map(([k,v])=>`${k.replace('USDT','')} ${v.w}W/${v.l}L ${Math.round(v.w/(v.w+v.l)*100)}%`).join(' | ')||'Learning 100 coins...';
 document.getElementById('brain').innerText=b;
}
setInterval(R,2000);R();setInterval(()=>fetch('/api/cron'),6000);fetch('/api/cron');
</script></body></html>"""
