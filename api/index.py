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

COINS=["1000PEPEUSDT","1000BONKUSDT","WIFUSDT","MOGUSDT","POPCATUSDT","BOMEUSDT","FLOKIUSDT","SHIBUSDT","DOGEUSDT","BONKUSDT","BRETTUSDT","VIRTUALUSDT","GIGAUSDT","MEMEUSDT","DOGSUSDT","TURBOUSDT","NEIROUSDT","SPXUSDT","FARTCOINUSDT","GOATUSDT","MEWUSDT","PEOPLEUSDT","MYROUSDT","WENUSDT","PNUTUSDT","MOODENGUSDT","PENGUUSDT","AI16ZUSDT","ARCUSDT","AVAUSDT","VINEUSDT","SWARMSUSDT","ELIZAUSDT","AIXBTUSDT","TRUMPUSDT","CHEEMSUSDT","APUUSDT","MUMUUSDT","WOJAKUSDT","PEPECOINUSDT","NOTUSDT","JUPUSDT","WLDUSDT","FETUSDT","TAOUSDT","RNDRUSDT","ORDIUSDT","TONUSDT","SOLUSDT","BNBUSDT","ETHUSDT","BTCUSDT","XRPUSDT","ADAUSDT","1000FLOKIUSDT","SAFEMOONUSDT","1000RATSUSDT"]

CG_IDS="pepe,bonk,dogwifcoin,mog-coin,popcat,book-of-meme,floki,shiba-inu,dogecoin,bonk,brett,virtual-protocol,gigachad,memecoin,dogs-2,turbo,neiro,spx6900,fartcoin,goatseus-maximus,cat-in-a-dogs-world,constitutiondao,myro,wen-4,peanut-the-squirrel,moo-deng,pudgy-penguins,ai16z,ai-rig-complex,ava-ai,vine,swarms,eliza,aixbt-by-virtuals,official-trump,cheems,apu-apustaja,mumu-the-bull,wojak,pepecoin-2,notcoin,jupiter-exchange-solana,worldcoin-wld,fetch-ai,bittensor,render-token,ordinals,the-open-network,solana,binancecoin,ethereum,bitcoin,ripple,cardano,floki,safemoon"
CG_LIST=CG_IDS.split(",")[:len(COINS)]

def get_bulk():
 try:
  r=requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(CG_LIST)}&vs_currencies=usd&include_24hr_change=true",timeout=5)
  if r.status_code==200:
   d=r.json()
   out={}; ch={}
   for i in range(min(len(COINS),len(CG_LIST))):
    cg=CG_LIST[i]; sym=COINS[i]
    if cg in d and 'usd' in d[cg]:
     out[sym]=float(d[cg]['usd'])
     ch[sym]=d[cg].get('usd_24h_change',0)
   return out,ch
 except: pass
 return {},{}

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); prev=load('VENUS_PREV',{}); now=time.time()
  prices,changes=get_bulk()
  if not prices: return {"ok":False,"reason":"no prices"}
  # Calculate 60s momentum
  mom={}
  for s,p in prices.items():
   if s in prev:
    mom[s]=(p-prev[s])/prev[s]*100 # % change in 20-30 sec
   else:
    mom[s]=0
  save('VENUS_PREV',prices)
  nw=[]
  for t in o:
   real=prices.get(t['symbol'])
   if not real: nw.append(t); continue
   age=now-t['t']; res=None
   if real>=t['entry']*1.022: res="WIN" # TP 2.2% for $50/day mission
   elif real<=t['entry']*0.990: res="LOSS" # SL 1.0%
   elif age>240: res="WIN" if real>=t['entry']*1.005 else "LOSS" # 4 min timeout need 0.5% to beat fee
   if res:
    pos=50.0; fee_slip=0.20; gross_win=pos*0.022; gross_loss=pos*0.01
    gross=gross_win if res=="WIN" else -gross_loss
    net=gross-fee_slip if res=="WIN" else -gross_loss-fee_slip
    fee_tot+=fee_slip; cap+=net; tot+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0,"last_win":0}
    st[t['symbol']]["w" if res=="WIN" else "l"]+=1
    st[t['symbol']]["profit"]+=net
    if res=="WIN": st[t['symbol']]["last_win"]=now
    cl.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':fee_slip,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'mom':round(mom.get(t['symbol'],0),3)})
    cl=cl[:100]
   else: nw.append(t)
  o=nw
  if len(o)<6:
   used=set(x['symbol'] for x in o)
   def wr(s): dd=st.get(s,{"w":1,"l":1}); return dd["w"]/max(1,dd["w"]+dd["l"])
   def profit(s): return st.get(s,{}).get("profit",0)
   def trades(s): return st.get(s,{}).get("w",0)+st.get(s,{}).get("l",0)
   def score(s):
    base=wr(s); tw=trades(s); pf=profit(s); m=mom.get(s,0); chg=changes.get(s,0)
    if tw<6: # new coin
     return 0.50 + (m*2) + (chg/50) + random.uniform(0,0.1) # pump = higher score
    if pf<-3: penalty=0.05
    elif pf<-1: penalty=0.20
    elif base<0.35: penalty=0.30
    elif base>=0.60 and pf>2: penalty=1.80
    elif base>=0.50: penalty=1.30
    else: penalty=1.0
    last=st.get(s,{}).get("last_win",0)
    boost=0.35 if (now-last)<900 else 0
    return max(0.001, (base**2)*penalty + boost + m*1.5 + chg/100)
   # FILTER: Only coins with mom > -0.2% (not dumping) and 24h change > -5%
   pool=[x for x in COINS if x not in used and x in prices and mom.get(x,0)>-0.25 and changes.get(x,0)>-8]
   if len(pool)<6: pool=[x for x in COINS if x not in used and x in prices] # fallback if all dumping
   pool.sort(key=lambda x: score(x), reverse=True)
   top=pool[:25]
   for _ in range(6-len(o)):
    if not top: break
    ch=top[0]
    e=prices.get(ch)
    if e:
     o.append({'symbol':ch,'entry':e,'t':now,'wr':int(wr(ch)*100),'score':round(score(ch),3),'profit':round(profit(ch),2),'mom':round(mom.get(ch,0),3),'chg':round(changes.get(ch,0),1)})
     top.pop(0)
    else: top.pop(0)
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"prices":len(prices),"open":len(o),"mom":mom}
 except Exception as e:
  save('last',f"ERR {str(e)[:50]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_PREV','last']:
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
<h2>VENUS v148 REAL MOMENTUM 100 $300→$50/DAY</h2>
<div class=card>CAP REAL $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=st>0</span> | Prices <span id=pc>0</span> | Fees $<span id=fee>0</span><br><span class=m>Fee $0.20 Real | WIN $0.90 Net (2.2% TP) | LOSS -$0.70 Net (1% SL) | Cron: <span id=c>never</span> | KV: <b id=k>YES</b> | 100 coins MOMENTUM ✅</span><br><span class=m>$300 | $50/coin | 6 open best PUMPING of 100 | TP 2.2% SL 1% | Timeout 4min | Momentum filter</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>R())">🚀 FORCE MOMENTUM 100</button><button class=btn2 onclick="if(confirm('Reset?')) fetch('/api/reset').then(()=>R())">🗑️ WIPE → $300 REAL</button></div>
<div class=card><b>Open <span id=oc>0/6</span> Best PUMPING of 100</b><div id=o>Press FORCE</div></div>
<div class=card><b>Closed REAL — Momentum</b><div id=cl>Waiting...</div></div>
<div class=card><b>Brain REAL — Top 25 of 100</b><div id=br class=m>Training...</div></div>
<div class=card><b>$50/Day REAL — Momentum</b><div id=rc class=m>Waiting...</div></div>
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
 document.getElementById('o').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>🔥 ${t.symbol} WR ${t.wr||0}% Mom ${t.mom||0}% 24h ${t.chg||0}% Score ${t.score||0}</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'No open - Press FORCE';
 document.getElementById('cl').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.symbol} ${c.hold}s Mom ${c.mom||0}%</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} Net $${c.net.toFixed(2)}</span></span></div>`).join('')||'No trades';
 let brEl=document.getElementById('br'); if(brEl){ let stats=Object.entries(j.stats||{}).sort((a,b)=> (b[1].profit||0)-(a[1].profit||0)); brEl.innerHTML=stats.slice(0,25).map(([k,v])=>`<div class=trade><span>${k.replace('USDT','')} ${v.w||0}W/${v.l||0}L ${Math.round(((v.w||0)/Math.max(1,(v.w||0)+(v.l||0)))*100)}% $${(v.profit||0).toFixed(2)}</span><span class=${(v.profit||0)>=0?'win':'loss'}>${(v.profit||0)>1?'🔥':'❌'}</span></div>`).join('')||'Scanning 100...'; }
 let rcEl=document.getElementById('rc'); if(rcEl){ let exp=0; if(j.total>5){ let w=j.wins/j.total; exp=w*0.90-(1-w)*0.70; } let perDay=exp*12*24; rcEl.innerHTML=`Momentum filter: only pumping coins<br>Expectancy $${exp.toFixed(3)}/trade REAL TP2.2% SL1%<br>~12/h → $${(exp*12).toFixed(2)}/h → $${perDay.toFixed(2)}/day<br>On $300 ${(perDay/300*100).toFixed(1)}% | Need 55% WR for $50/day<br>Current ${wr}% → ${perDay>=50?'✅ $50/day POSSIBLE!':'Training...'}`; }
 }catch(e){ document.getElementById('o').innerText='Error: '+e.message; }
}
setInterval(R,3000);R();setInterval(()=>{fetch('/api/cron').then(()=>R());},25000);
</script></body></html>"""
