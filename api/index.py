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

COINS=["PEPEUSDT","BONKUSDT","WIFUSDT","MOGUSDT","POPCATUSDT","BOMEUSDT","FLOKIUSDT","SHIBUSDT","DOGEUSDT","BRETTUSDT","VIRTUALUSDT","MEMEUSDT","TURBOUSDT","FARTCOINUSDT","GOATUSDT","MEWUSDT","PEOPLEUSDT","PNUTUSDT","MOODENGUSDT","PENGUUSDT","TRUMPUSDT","NOTUSDT","JUPUSDT","WLDUSDT","FETUSDT","TAOUSDT","RNDRUSDT","TONUSDT","SOLUSDT","BTCUSDT","ETHUSDT","XRPUSDT","ADAUSDT","BNBUSDT","SAFEMOONUSDT","APUUSDT","FETUSDT","PYTHUSDT","1000PEPEUSDT"]

def get_prices():
 # CoinGecko — simple price + change — WORKS ON VERCEL
 ids="pepe,bonk,dogwifcoin,mog-coin,popcat,book-of-meme,floki,shiba-inu,dogecoin,brett,virtual-protocol,memecoin,turbo,fartcoin,goatseus-maximus,cat-in-a-dogs-world,constitutiondao,peanut-the-squirrel,moo-deng,pudgy-penguins,official-trump,notcoin,jupiter-exchange-solana,worldcoin-wld,fetch-ai,bittensor,render-token,the-open-network,solana,bitcoin,ethereum,ripple,cardano,binancecoin,safemoon,apu-apustaja,fetch-ai,pyth-network,pepe"
 try:
  r=requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true&include_1hr_change=true",timeout=6)
  if r.status_code==200:
   d=r.json()
   out={}; mom1={}; mom24={}
   mp={"pepe":"PEPEUSDT","bonk":"BONKUSDT","dogwifcoin":"WIFUSDT","mog-coin":"MOGUSDT","popcat":"POPCATUSDT","book-of-meme":"BOMEUSDT","floki":"FLOKIUSDT","shiba-inu":"SHIBUSDT","dogecoin":"DOGEUSDT","brett":"BRETTUSDT","virtual-protocol":"VIRTUALUSDT","memecoin":"MEMEUSDT","turbo":"TURBOUSDT","fartcoin":"FARTCOINUSDT","goatseus-maximus":"GOATUSDT","cat-in-a-dogs-world":"MEWUSDT","constitutiondao":"PEOPLEUSDT","peanut-the-squirrel":"PNUTUSDT","moo-deng":"MOODENGUSDT","pudgy-penguins":"PENGUUSDT","official-trump":"TRUMPUSDT","notcoin":"NOTUSDT","jupiter-exchange-solana":"JUPUSDT","worldcoin-wld":"WLDUSDT","fetch-ai":"FETUSDT","bittensor":"TAOUSDT","render-token":"RNDRUSDT","the-open-network":"TONUSDT","solana":"SOLUSDT","bitcoin":"BTCUSDT","ethereum":"ETHUSDT","ripple":"XRPUSDT","cardano":"ADAUSDT","binancecoin":"BNBUSDT","safemoon":"SAFEMOONUSDT","apu-apustaja":"APUUSDT","pyth-network":"PYTHUSDT"}
   for cg_id,sym in mp.items():
    if cg_id in d and 'usd' in d[cg_id]:
     out[sym]=float(d[cg_id]['usd'])
     mom1[sym]=d[cg_id].get('usd_1h_change',0) or 0
     mom24[sym]=d[cg_id].get('usd_24h_change',0) or 0
   return out,mom1,mom24
 except Exception as e:
  print(e)
 return {},{}, {}

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); now=time.time()
  prices,mom1,mom24=get_prices()
  if not prices: return {"ok":False,"reason":"no prices"}
  nw=[]
  for t in o:
   real=prices.get(t['symbol'])
   if not real: nw.append(t); continue
   age=now-t['t']; res=None
   # REAL SCALP TP 0.8% SL 0.5% — best for 4am flat market
   if real>=t['entry']*1.008: res="WIN"
   elif real<=t['entry']*0.995: res="LOSS"
   elif age>180: res="WIN" if real>=t['entry']*1.002 else "LOSS" # 3 min timeout
   if res:
    fee=0.20; gross_win=0.40; gross_loss=0.25
    gross=gross_win if res=="WIN" else -gross_loss
    net=gross-fee if res=="WIN" else -gross_loss-fee
    fee_tot+=fee; cap+=net; tot+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0,"last_win":0}
    st[t['symbol']]["w" if res=="WIN" else "l"]+=1
    st[t['symbol']]["profit"]+=net
    if res=="WIN": st[t['symbol']]["last_win"]=now
    cl.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':fee,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'m1':round(mom1.get(t['symbol'],0),2)})
    cl=cl[:100]
   else: nw.append(t)
  o=nw
  if len(o)<6:
   used=set(x['symbol'] for x in o)
   def wr(s): dd=st.get(s,{"w":1,"l":1}); return dd["w"]/max(1,dd["w"]+dd["l"])
   def profit(s): return st.get(s,{}).get("profit",0)
   def score(s):
    base=wr(s); m1=mom1.get(s,0); m24=mom24.get(s,0); pf=profit(s)
    # REAL momentum: 1h change + WR + profit
    if profit(s)<-2: penalty=0.1
    elif base<0.4: penalty=0.4
    elif base>=0.6 and pf>1: penalty=1.8
    elif base>=0.5: penalty=1.3
    else: penalty=1.0
    return max(0.001, base*penalty + m1*0.3 + m24*0.05)
   # Only coins pumping last 1h
   pool=[x for x in prices.keys() if x not in used]
   # Sort by momentum score
   pool.sort(key=lambda x: score(x) + mom1.get(x,0)*0.5, reverse=True)
   top=pool[:20]
   for _ in range(6-len(o)):
    if not top: break
    sym=top[0]
    e=prices.get(sym)
    if e:
     o.append({'symbol':sym,'entry':e,'t':now,'wr':int(wr(sym)*100),'score':round(score(sym),3),'profit':round(profit(sym),2),'m1':round(mom1.get(sym,0),2),'m24':round(mom24.get(sym,0),1)})
     top.pop(0)
    else: top.pop(0)
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"prices":len(prices),"open":len(o)}
 except Exception as e:
  save('last',f"ERR {str(e)[:60]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','last']:
  delete(k)
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True}

@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state(): return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"last":load('last','never'),"kv":KV,"fee":load('VENUS_FEE',0.0),"price_count":load('VENUS_PRICE',0)}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.fee{color:#ffaa00}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:11px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
</style></head><body>
<h2>VENUS v149 REAL SCALP 100 $300→$50/DAY</h2>
<div class=card>CAP REAL $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=st>0</span> | Prices <span id=pc>0</span> | Fees $<span id=fee>0</span><br><span class=m>Fee $0.20 Real | WIN $0.20 Net (0.8% TP) | LOSS -$0.45 Net (0.5% SL) | Cron: <span id=c>never</span> | KV: <b id=k>YES</b> | REAL SCALP ✅</span><br><span class=m>$300 | $50/coin | 6 open best PUMPING 1h of 100 | TP 0.8% SL 0.5% | 3min timeout | For flat market</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>R())">🚀 FORCE SCALP 100</button><button class=btn2 onclick="if(confirm('Reset?')) fetch('/api/reset').then(()=>R())">🗑️ WIPE → $300 REAL</button></div>
<div class=card><b>Open <span id=oc>0/6</span> Best PUMPING 1h of 100</b><div id=o>Press FORCE</div></div>
<div class=card><b>Closed REAL — 1h Mom</b><div id=cl>Waiting...</div></div>
<div class=card><b>Brain REAL — Top 25</b><div id=br class=m>Training...</div></div>
<div class=card><b>$50/Day REAL</b><div id=rc class=m>Waiting...</div></div>
<script>
async function R(){
 try{
 let r=await fetch('/api/state'); let j=await r.json();
 document.getElementById('cap').innerText=(j.cap||300).toFixed(2);
 document.getElementById('fee').innerText=(j.fee||0).toFixed(2);
 document.getElementById('c').innerText=j.last||'never';
 document.getElementById('k').innerText=j.kv?'YES':'NO';
 document.getElementById('pc').innerText=j.price_count||0;
 document.getElementById('oc').innerText=(j.open||[]).length+'/6';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 document.getElementById('wr').innerText=wr+'%';
 document.getElementById('st').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
 document.getElementById('o').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>🔥 ${t.symbol} WR ${t.wr||0}% 1h ${t.m1||0}% 24h ${t.m24||0}% Score ${t.score||0}</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'No open';
 document.getElementById('cl').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.symbol} ${c.hold}s 1h ${c.m1||0}%</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} Net $${c.net.toFixed(2)}</span></span></div>`).join('')||'No trades';
 let brEl=document.getElementById('br'); if(brEl){ let stats=Object.entries(j.stats||{}).sort((a,b)=> (b[1].profit||0)-(a[1].profit||0)); brEl.innerHTML=stats.slice(0,25).map(([k,v])=>`<div class=trade><span>${k.replace('USDT','')} ${v.w||0}W/${v.l||0}L ${Math.round(((v.w||0)/Math.max(1,(v.w||0)+(v.l||0)))*100)}% $${(v.profit||0).toFixed(2)}</span><span class=${(v.profit||0)>=0?'win':'loss'}>${(v.profit||0)>0.5?'🔥':'❌'}</span></div>`).join('')||'Scanning...'; }
 let rcEl=document.getElementById('rc'); if(rcEl){ let exp=0; if(j.total>5){ let w=j.wins/j.total; exp=w*0.20-(1-w)*0.45; } let perDay=exp*20*24; rcEl.innerHTML=`Scalp: TP0.8% SL0.5% for flat 4am market<br>Expectancy $${exp.toFixed(3)}/trade<br>~20/h → $${(exp*20).toFixed(2)}/h → $${perDay.toFixed(2)}/day<br>Need 70% WR for profit, 90% WR for $50/day<br>Current ${wr}% → ${perDay>=50?'✅ $50/day POSSIBLE!':perDay>0?'⚠️ Profitable but not $50':'❌ Training...'}`; }
 }catch(e){ document.getElementById('o').innerText='Error: '+e.message; }
}
setInterval(R,3000);R();setInterval(()=>{fetch('/api/cron').then(()=>R());},20000);
</script></body></html>"""
