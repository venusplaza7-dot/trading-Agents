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
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); prev=load('VENUS_PREV',{}); banned=load('VENUS_BANNED',{}); now=time.time()
  prices,m24=get_prices()
  if not prices:
   return {"ok":False}
  # REAL 20sec momentum from our own prev - THIS WORKS, not CoinGecko Mom 0% bug
  mom={}
  for s,p in prices.items():
   if s in prev: mom[s]=(p-prev[s])/prev[s]*100
   else: mom[s]=0
  save('VENUS_PREV',prices)
  # Unban coins after 1 hour
  for s in list(banned.keys()):
   if now-banned[s]>3600: del banned[s]
  save('VENUS_BANNED',banned)
  nw=[]
  for t in o:
   real=prices.get(t['symbol'])
   if not real:
    if now-t.get('t',now)>90: 
     tot+=1; fee_tot+=0.20; cap+=-0.45
     if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0}
     st[t['symbol']]["l"]+=1; st[t['symbol']]["profit"]+=-0.45
     cl.insert(0,{'symbol':t['symbol'],'net':-0.45,'result':'LOSS','time':datetime.now().strftime("%H:%M:%S"),'hold':int(now-t.get('t',now)),'mode':t.get('mode','SHORT')})
     # Ban if 0W/3L
     if st[t['symbol']]["w"]==0 and st[t['symbol']]["l"]>=3: banned[t['symbol']]=now
    else: nw.append(t)
    continue
   age=now-t.get('t',now); res=None
   tm=t.get('mode','SHORT')
   # SMART TP/SL for 90% WR: SHORT needs to drop 0.7% to win, pump 0.6% to lose
   if tm=="SHORT":
    if real<=t['entry']*0.993: res="WIN" # drop 0.7% = WIN $0.15 net
    elif real>=t['entry']*1.006: res="LOSS" # pump 0.6% = LOSS $-0.50
    elif age>75: res="WIN" if real<=t['entry']*0.999 else "LOSS" # 75s timeout
   else:
    if real>=t['entry']*1.007: res="WIN"
    elif real<=t['entry']*0.994: res="LOSS"
    elif age>75: res="WIN" if real>=t['entry']*1.001 else "LOSS"
   if res:
    fee=0.20
    if tm=="SHORT": gw=0.35; gl=0.30 # WIN $0.15 net LOSS $-0.50 net - risk/reward for 90% WR
    else: gw=0.35; gl=0.30
    gross=gw if res=="WIN" else -gl
    net=gross-fee if res=="WIN" else -gl-fee
    fee_tot+=fee; cap+=net; tot+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0,"last_win":0}
    st[t['symbol']]["w" if res=="WIN" else "l"]+=1
    st[t['symbol']]["profit"]+=net
    if res=="WIN": st[t['symbol']]["last_win"]=now
    else:
     # Ban if 0W/3L in a row
     if st[t['symbol']]["w"]==0 and st[t['symbol']]["l"]>=3: banned[t['symbol']]=now
    cl.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':fee,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'m':round(mom.get(t['symbol'],0),3),'m24':round(m24.get(t['symbol'],0),1),'mode':tm})
    cl=cl[:150]
   else: nw.append(t)
  o=nw
  # SELECTIVE: Trade only 2 coins at a time, BEST coins only!
  if len(o)<2:
   used=set(x.get('symbol') for x in o)
   def wr(s): dd=st.get(s,{"w":1,"l":1}); return dd["w"]/max(1,dd["w"]+dd["l"])
   def profit(s): return st.get(s,{}).get("profit",0)
   def score(s):
    # Score for 90% WR: profit + WR + recent win + mom + 24h
    base=wr(s); pf=profit(s); m=mom.get(s,0); m24v=m24.get(s,0)
    last_win=st.get(s,{}).get("last_win",0)
    recent_bonus=0.5 if (now-last_win)<600 else 0.2 if (now-last_win)<1800 else 0
    return base*1.5 + pf*0.3 + m*2 + m24v*0.08 + recent_bonus
   # Filter: NOT banned, NOT 0W/3L, mom >0.02% pumping to short
   pool=[]
   for s in prices.keys():
    if s in used: continue
    if s in banned: continue
    st_s=st.get(s,{"w":0,"l":0})
    if st_s["w"]==0 and st_s["l"]>=3: continue # skip losers
    if st_s["w"]==0 and st_s["l"]>=2 and profit(s)<-1: continue
    pool.append(s)
   # For SHORT mode: pick most pumped
   pool.sort(key=lambda x: (mom.get(x,0), m24.get(x,0), score(x)), reverse=True)
   # Only trade if mom >0.02% (real pump) AND 24h > -5% (not crashing)
   good=[x for x in pool if mom.get(x,0)>0.02 and m24.get(x,0)>-5]
   # If no good, WAIT! Don't force trade!
   if len(good)>=1:
    top=good[:3]
   else:
    top=[] # WAIT - no trade is better than losing trade!
   for _ in range(2-len(o)):
    if not top: break
    sym=top[0]
    e=prices.get(sym)
    if e:
     o.append({'symbol':sym,'entry':e,'t':now,'wr':int(wr(sym)*100),'m':round(mom.get(sym,0),3),'m24':round(m24.get(sym,0),1),'mode':'SHORT','score':round(score(sym),3)})
     top.pop(0)
    else: top.pop(0)
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices)); save('VENUS_BANNED',banned)
  return {"ok":True,"prices":len(prices),"open":len(o),"banned":len(banned),"mode":"SHORT_SELECTIVE"}
 except Exception as e:
  save('last',f"ERR {str(e)[:80]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_PREV','VENUS_BANNED','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('VENUS_PRICE',0); save('last',datetime.now().strftime("%H:%M:%S")); save('VENUS_BANNED',{})
 return {"reset":True}

@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state(): return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"last":load('last','never'),"kv":KV,"fee":load('VENUS_FEE',0.0),"price_count":load('VENUS_PRICE',0),"banned":load('VENUS_BANNED',{})}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:11px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
</style></head><body>
<h2>VENUS v156 SELECTIVE 2-COIN 90% WR $300→$50/DAY</h2>
<div class=card>CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/2</span> | Banned <span id=bn>0</span> | Prices <span id=pc>0</span> | Fees $<span id=fee>0</span><br><span class=m>SELECTIVE: 2 coins only! | SHORT WIN $0.15 (drop 0.7%) | LOSS $-0.50 (pump 0.6%) | 75s timeout | Picks only if Mom>0.02% | Bans 0W/3L for 1h | Waits if no good coin!</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | 90% WR MODE ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,800))">🚀 FORCE SELECTIVE 2-COIN</button><button class=btn2 onclick="if(confirm('WIPE $141 to $300 SELECTIVE 90% WR?')){fetch('/api/reset').then(()=>setTimeout(loadState,800))}">🗑️ WIPE → $300 SELECTIVE 90% WR</button></div>
<div class=card><b>Open <span id=oc2>0/2</span> BEST 2 only - waits if no good</b><div id=open>Press FORCE - will wait if no pump</div></div>
<div class=card><b>Closed SELECTIVE</b><div id=closed>Waiting...</div></div>
<div class=card><b>Brain SELECTIVE - bans losers</b><div id=brain class=m>Training...</div></div>
<div class=card><b>Banned coins (0W/3L)</b><div id=banned class=m>None - good!</div></div>
<div class=card><b>$50/Day 90% WR</b><div id=calc class=m>Waiting...</div></div>
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
  if(el('bn')) el('bn').innerText=Object.keys(j.banned||{}).length;
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/2';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/2';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>🔻 SHORT ${t.symbol} WR ${t.wr||0}% Mom ${t.m||0}% 24h ${t.m24||0}% Score ${t.score||0}</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'Waiting for best pump - no forced trades (good!)';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} SHORT ${c.symbol} ${c.hold}s Mom ${c.m||0}%</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${(c.net||0).toFixed(2)}</span></span></div>`).join('')||'No trades yet';
  if(el('brain')){ let stats=Object.entries(j.stats||{}).sort((a,b)=>(b[1].profit||0)-(a[1].profit||0)); el('brain').innerHTML=stats.slice(0,20).map(([k,v])=>`<div class=trade><span>${k.replace('USDT','')} ${v.w||0}W/${v.l||0}L ${Math.round(((v.w||0)/Math.max(1,(v.w||0)+(v.l||0)))*100)}% $${(v.profit||0).toFixed(2)}</span><span class=${(v.profit||0)>=0?'win':'loss'}>${(v.profit||0)>0?'🔥':v.l>=3?'🚫 Banned':'❌'}</span></div>`).join('')||'Scanning...'; }
  if(el('banned')){ let b=Object.keys(j.banned||{}); el('banned').innerHTML=b.length?b.map(s=>`<span>${s} 🚫 banned 1h</span>`).join('<br>'):'None - all coins good!'; }
  if(el('calc')){ let exp=0; if(j.total>10){ let w=j.wins/j.total; exp=w*0.15-(1-w)*0.50; } let perDay=exp*20*24; el('calc').innerHTML=`SELECTIVE 2 coins only, waits if no good<br>Expectancy $${exp.toFixed(3)}/trade WIN $0.15 LOSS $-0.50<br>~20/h → $${(exp*20).toFixed(2)}/h → $${perDay.toFixed(2)}/day<br>Need 77% WR for profit, 85% WR for $50/day<br>Current ${wr}% → ${perDay>=50?'✅ $50/day POSSIBLE!':perDay>0?'⚠️ Profitable with 90% WR potential':'❌ Waiting for best coin...'}`; }
 }catch(e){ let el=document.getElementById('open'); if(el) el.innerText='Error: '+e.message; }
}
setInterval(loadState,3000); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},20000);
</script></body></html>"""
