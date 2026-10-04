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

COINS=["PEPEUSDT","BONKUSDT","WIFUSDT","FLOKIUSDT","DOGEUSDT","SHIBUSDT","BRETTUSDT","POPCATUSDT","MOGUSDT","TURBOUSDT","FARTCOINUSDT","MEWUSDT","PENGUUSDT","TRUMPUSDT","NOTUSDT","WLDUSDT","TAOUSDT","GOATUSDT","VIRTUALUSDT","FETUSDT","SOLUSDT","PYTHUSDT"]

def get_prices():
 ids="pepe,bonk,dogwifcoin,floki,dogecoin,shiba-inu,brett,popcat,mog-coin,turbo,fartcoin,cat-in-a-dogs-world,pudgy-penguins,official-trump,notcoin,worldcoin-wld,bittensor,goatseus-maximus,virtual-protocol,fetch-ai,solana,pyth-network"
 try:
  r=requests.get(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&price_change_percentage=24h&per_page=30&page=1",timeout=6)
  if r.status_code==200:
   data=r.json()
   mp={"pepe":"PEPEUSDT","bonk":"BONKUSDT","dogwifcoin":"WIFUSDT","floki":"FLOKIUSDT","dogecoin":"DOGEUSDT","shiba-inu":"SHIBUSDT","brett":"BRETTUSDT","popcat":"POPCATUSDT","mog-coin":"MOGUSDT","turbo":"TURBOUSDT","fartcoin":"FARTCOINUSDT","cat-in-a-dogs-world":"MEWUSDT","pudgy-penguins":"PENGUUSDT","official-trump":"TRUMPUSDT","notcoin":"NOTUSDT","worldcoin-wld":"WLDUSDT","bittensor":"TAOUSDT","goatseus-maximus":"GOATUSDT","virtual-protocol":"VIRTUALUSDT","fetch-ai":"FETUSDT","solana":"SOLUSDT","pyth-network":"PYTHUSDT"}
   out={}; m24={}
   for c in data:
    sym=mp.get(c['id'])
    if sym:
     out[sym]=float(c['current_price'])
     m24[sym]=c.get('price_change_percentage_24h',0) or 0
   return out,m24
 except: pass
 return {},{}

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); prev=load('VENUS_PREV',{}); now=time.time()
  prices,m24=get_prices()
  if not prices:
   nw=[]
   for t in o:
    if now-t.get('t',now)>90:
     tot+=1; fee_tot+=0.20; cap+=-0.45
     if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0}
     st[t['symbol']]["l"]+=1; st[t['symbol']]["profit"]+=-0.45
     cl.insert(0,{'symbol':t['symbol'],'net':-0.45,'result':'LOSS','time':datetime.now().strftime("%H:%M:%S"),'hold':int(now-t.get('t',now)),'mode':t.get('mode','LONG')})
    else: nw.append(t)
   save('VENUS_OPEN',nw); save('VENUS_CLOSED',cl[:120]); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_FEE',fee_tot); save('VENUS_STATS',st)
   return {"ok":False}
  mom={}
  for s,p in prices.items():
   if s in prev: mom[s]=(p-prev[s])/prev[s]*100
   else: mom[s]=0
  save('VENUS_PREV',prices)
  # SMART: Check last 20 trades WR - if <40% FLIP MODE!
  recent=cl[:20]
  recent_wr = (sum(1 for x in recent if x.get('result')=='WIN')/len(recent)*100) if len(recent)>=10 else 50
  # Determine MODE based on REAL performance + volatility
  avg_mom = sum(abs(v) for v in mom.values())/max(1,len(mom))
  if recent_wr < 38 and len(recent)>=12:
   mode="SHORT" # losing long -> reverse to short!
  elif recent_wr > 62 and len(recent)>=12:
   mode="LONG" # winning long -> keep long
  elif avg_mom < 0.08: # flat market 4am
   mode="SHORT" # mean reversion short
  else:
   mode="LONG" # trending market
  save('VENUS_MODE',mode)
  save('VENUS_RECENT_WR',recent_wr)
  nw=[]
  for t in o:
   real=prices.get(t['symbol'])
   if not real:
    if now-t.get('t',now)>75:
     tot+=1; fee_tot+=0.20; cap+=-0.45
     if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0}
     st[t['symbol']]["l"]+=1; st[t['symbol']]["profit"]+=-0.45
     cl.insert(0,{'symbol':t['symbol'],'net':-0.45,'result':'LOSS','time':datetime.now().strftime("%H:%M:%S"),'hold':int(now-t.get('t',now)),'mode':t.get('mode','LONG')})
    else: nw.append(t)
    continue
   age=now-t.get('t',now); res=None
   tm=t.get('mode','LONG')
   if tm=="SHORT":
    if real<=t['entry']*0.991: res="WIN"
    elif real>=t['entry']*1.005: res="LOSS"
    elif age>85: res="WIN" if real<=t['entry']*0.998 else "LOSS"
   else: # LONG
    if real>=t['entry']*1.009: res="WIN"
    elif real<=t['entry']*0.995: res="LOSS"
    elif age>110: res="WIN" if real>=t['entry']*1.002 else "LOSS"
   if res:
    fee=0.20
    if tm=="SHORT": gw=0.45; gl=0.25
    else: gw=0.45; gl=0.25
    gross=gw if res=="WIN" else -gl
    net=gross-fee if res=="WIN" else -gl-fee
    fee_tot+=fee; cap+=net; tot+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0,"last_win":0}
    st[t['symbol']]["w" if res=="WIN" else "l"]+=1
    st[t['symbol']]["profit"]+=net
    if res=="WIN": st[t['symbol']]["last_win"]=now
    cl.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':fee,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'m':round(mom.get(t['symbol'],0),3),'m24':round(m24.get(t['symbol'],0),1),'mode':tm})
    cl=cl[:150]
   else: nw.append(t)
  o=nw
  if len(o)<6:
   used=set(x.get('symbol') for x in o)
   def wr(s): dd=st.get(s,{"w":1,"l":1}); return dd["w"]/max(1,dd["w"]+dd["l"])
   pool=[x for x in prices.keys() if x not in used]
   if mode=="SHORT":
    pool.sort(key=lambda x: mom.get(x,0), reverse=True) # most pumped to short
    top=[x for x in pool if mom.get(x,0)>0.02][:12] or pool[:12]
   else:
    pool.sort(key=lambda x: (mom.get(x,0)+m24.get(x,0)*0.1), reverse=True)
    top=[x for x in pool if mom.get(x,0)>0.04][:12] or pool[:12]
   for _ in range(6-len(o)):
    if not top: break
    sym=top[0]
    e=prices.get(sym)
    if e:
     o.append({'symbol':sym,'entry':e,'t':now,'wr':int(wr(sym)*100),'m':round(mom.get(sym,0),3),'m24':round(m24.get(sym,0),1),'mode':mode})
     top.pop(0)
    else: top.pop(0)
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"prices":len(prices),"open":len(o),"mode":mode,"recent_wr":recent_wr}
 except Exception as e:
  save('last',f"ERR {str(e)[:80]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_PREV','VENUS_MODE','VENUS_RECENT_WR','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('VENUS_PRICE',0); save('last',datetime.now().strftime("%H:%M:%S")); save('VENUS_MODE','SHORT'); save('VENUS_RECENT_WR',50)
 return {"reset":True}

@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state(): return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"last":load('last','never'),"kv":KV,"fee":load('VENUS_FEE',0.0),"price_count":load('VENUS_PRICE',0),"mode":load('VENUS_MODE','SHORT'),"recent_wr":load('VENUS_RECENT_WR',50)}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:11px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
</style></head><body>
<h2>VENUS v155 SMART ADAPTIVE $300→$50/DAY</h2>
<div class=card>CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Mode <b><span id=mode>SHORT</span></b> | Prices <span id=pc>0</span> | Fees $<span id=fee>0</span><br><span class=m>Recent 20 WR <span id=rwr>50%</span> | SHORT WIN $0.25 drop 0.9% | LONG WIN $0.25 pump 0.9% | Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | SMART ADAPTIVE ✅</span><br><span class=m>SMART: If recent WR <38% → FLIP to SHORT! If >62% → LONG! Flat market (<0.08% vol) → SHORT mean reversion | Trending → LONG momentum</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,800))">🚀 FORCE SMART ADAPTIVE</button><button class=btn2 onclick="if(confirm('WIPE $160 to $300 SMART?')){fetch('/api/reset').then(()=>setTimeout(loadState,800))}">🗑️ WIPE → $300 SMART ADAPTIVE</button></div>
<div class=card><b>Open <span id=oc>0/6</span> Mode <span id=ocm>SHORT</span></b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed SMART</b><div id=closed>Waiting...</div></div>
<div class=card><b>Brain SMART</b><div id=brain class=m>Training...</div></div>
<div class=card><b>$50/Day SMART</b><div id=calc class=m>Waiting...</div></div>
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
  if(el('mode')) el('mode').innerText=j.mode||'SHORT';
  if(el('ocm')) el('ocm').innerText=j.mode||'SHORT';
  if(el('rwr')) el('rwr').innerText=Math.round(j.recent_wr||50)+'%';
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/6';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode=='SHORT'?'🔻 SHORT':'🔥 LONG'} ${t.symbol} WR ${t.wr||0}% Mom ${t.m||0}% 24h ${t.m24||0}%</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'No open';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode||'LONG'} ${c.symbol} ${c.hold}s Mom ${c.m||0}%</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${(c.net||0).toFixed(2)}</span></span></div>`).join('')||'No trades';
  if(el('brain')){ let stats=Object.entries(j.stats||{}).sort((a,b)=>(b[1].profit||0)-(a[1].profit||0)); el('brain').innerHTML=stats.slice(0,20).map(([k,v])=>`<div class=trade><span>${k.replace('USDT','')} ${v.w||0}W/${v.l||0}L ${Math.round(((v.w||0)/Math.max(1,(v.w||0)+(v.l||0)))*100)}% $${(v.profit||0).toFixed(2)}</span><span class=${(v.profit||0)>=0?'win':'loss'}>${(v.profit||0)>0.5?'🔥':'❌'}</span></div>`).join('')||'Scanning...'; }
  if(el('calc')){ let exp=0; if(j.total>5){ let w=j.wins/j.total; exp=w*0.25-(1-w)*0.45; } let perDay=exp*40*24; el('calc').innerHTML=`Mode: ${j.mode} | Recent 20 WR ${Math.round(j.recent_wr||50)}%<br>Expectancy $${exp.toFixed(3)}/trade<br>~40/h → $${(exp*40).toFixed(2)}/h → $${perDay.toFixed(2)}/day<br>SMART flips when losing! Current ${wr}% → ${perDay>=50?'✅ $50/day POSSIBLE!':perDay>0?'⚠️ Profitable':'❌ Training...'}`; }
 }catch(e){ let el=document.getElementById('open'); if(el) el.innerText='Error: '+e.message; }
}
setInterval(loadState,3000); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},15000);
</script></body></html>"""
