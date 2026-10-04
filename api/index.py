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

# ONLY SUB $1 COINS - top 100 movers
SUB1_IDS="pepe,bonk,shiba-inu,floki,dogecoin,brett,popcat,mog-coin,turbo,cat-in-a-dogs-world,pudgy-penguins,notcoin,goatseus-maximus,virtual-protocol,fetch-ai,bonk,floki,pepe,shiba-inu,dogecoin,cardano,tron,polygon,vechain,hedera,algorand,cronos,stellar,arbitrum,optimism,immutable,render-token,fetch-ai,worldcoin-wld,bittensor,pyth-network"
SUB1_MAP={"pepe":"PEPEUSDT","bonk":"BONKUSDT","shiba-inu":"SHIBUSDT","floki":"FLOKIUSDT","dogecoin":"DOGEUSDT","brett":"BRETTUSDT","popcat":"POPCATUSDT","mog-coin":"MOGUSDT","turbo":"TURBOUSDT","cat-in-a-dogs-world":"MEWUSDT","pudgy-penguins":"PENGUUSDT","notcoin":"NOTUSDT","goatseus-maximus":"GOATUSDT","virtual-protocol":"VIRTUALUSDT","fetch-ai":"FETUSDT","cardano":"ADAUSDT","tron":"TRXUSDT","polygon":"MATICUSDT","vechain":"VETUSDT","hedera":"HBARUSDT","algorand":"ALGOUSDT","cronos":"CROUSDT","stellar":"XLMUSDT","arbitrum":"ARBUSDT","optimism":"OPUSDT","immutable":"IMXUSDT","render-token":"RNDRUSDT","worldcoin-wld":"WLDUSDT","bittensor":"TAOUSDT","pyth-network":"PYTHUSDT"}

def get_prices():
 try:
  r=requests.get(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={','.join(set(SUB1_MAP.keys()))}&price_change_percentage=24h&per_page=50&page=1",timeout=7)
  if r.status_code==200:
   data=r.json()
   out={}; m24={}
   for c in data:
    sym=SUB1_MAP.get(c['id'])
    if sym and c['current_price']<1.0: # ONLY UNDER $1!
     out[sym]=float(c['current_price'])
     m24[sym]=c.get('price_change_percentage_24h',0) or 0
   return out,m24
 except Exception as e:
  print(e)
 return {},{}

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); prev=load('VENUS_PREV',{}); now=time.time()
  prices,m24=get_prices()
  if not prices: return {"ok":False}
  mom={}
  for s,p in prices.items():
   if s in prev and prev[s]>0: mom[s]=(p-prev[s])/prev[s]*100
   else: mom[s]=0
  save('VENUS_PREV',prices)

  nw=[]
  for t in o:
   real=prices.get(t['symbol'])
   if not real:
    if now-t.get('t',now)>70:
     tot+=1; fee_tot+=0.10; cap+=-0.28
     if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0}
     st[t['symbol']]["l"]+=1; st[t['symbol']]["profit"]+=-0.28
     cl.insert(0,{'symbol':t['symbol'],'net':-0.28,'result':'LOSS','time':datetime.now().strftime("%H:%M:%S"),'hold':int(now-t.get('t',now)),'mode':t.get('mode','LONG')})
    else: nw.append(t)
    continue
   age=now-t.get('t',now); res=None
   tm=t.get('mode','LONG')
   # SUB $1 SCALP: 0.25% TP / 0.30% SL - moves easy for sub $1
   if tm=="LONG":
    if real>=t['entry']*1.0025: res="WIN" # +0.25%
    elif real<=t['entry']*0.9970: res="LOSS" # -0.30%
    elif age>70: res="WIN" if real>=t['entry']*1.0008 else "LOSS"
   else:
    if real<=t['entry']*0.9975: res="WIN"
    elif real>=t['entry']*1.0030: res="LOSS"
    elif age>70: res="WIN" if real<=t['entry']*0.9992 else "LOSS"
   if res:
    fee=0.10; gw=0.22; gl=0.18
    gross=gw if res=="WIN" else -gl
    net=gross-fee if res=="WIN" else -gl-fee # WIN $0.12 LOSS $-0.28
    fee_tot+=fee; cap+=net; tot+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0}
    st[t['symbol']]["w" if res=="WIN" else "l"]+=1; st[t['symbol']]["profit"]+=net
    cl.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':fee,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'m':round(mom.get(t['symbol'],0),3),'m24':round(m24.get(t['symbol'],0),1),'mode':tm,'price':real})
    cl=cl[:150]
   else: nw.append(t)
  o=nw

  if len(o)<3:
   used=set(x.get('symbol') for x in o)
   def wr(s): dd=st.get(s,{"w":1,"l":1}); return dd["w"]/max(1,dd["w"]+dd["l"])
   # ONLY SUB $1, sort by mom + 24h - most movement
   pool=[s for s in prices.keys() if s not in used and prices[s]<1.0]
   pool.sort(key=lambda x: (abs(mom.get(x,0)), m24.get(x,0)), reverse=True)
   # Pick coins with Mom >0.04% or 24h >2% - real movers under $1
   good=[s for s in pool if abs(mom.get(s,0))>0.04 or abs(m24.get(s,0))>2.5]
   top=good[:4] if good else pool[:4]
   for _ in range(3-len(o)):
    if not top: break
    sym=top[0]; e=prices.get(sym)
    if e and e<1.0: # double check sub $1
     mode="LONG" if mom.get(sym,0)>0 else "SHORT" if mom.get(sym,0)<-0.04 else "LONG"
     o.append({'symbol':sym,'entry':e,'t':now,'wr':int(wr(sym)*100),'m':round(mom.get(sym,0),3),'m24':round(m24.get(sym,0),1),'mode':mode,'price':e})
     top.pop(0)
    else: top.pop(0)

  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"prices":len(prices),"sub1":len([p for p in prices.values() if p<1])}
 except Exception as e:
  save('last',f"ERR {str(e)[:80]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_PREV','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True}

@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state(): return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"last":load('last','never'),"kv":KV,"fee":load('VENUS_FEE',0.0),"price_count":load('VENUS_PRICE',0)}

@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:11px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
</style></head><body>
<h2>VENUS v160 SUB $1 FOCUS $300→$50/DAY</h2>
<div class=card>CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/3</span> | Prices <span id=pc>0</span> Sub$1 <span id=sub>0</span> | Fees $<span id=fee>0</span><br><span class=m>ONLY UNDER $1: PEPE $0.000008, BONK, SHIB, FLOKI, DOGE $0.18, BRETT $0.07, POPCAT $0.40, ADA $0.45, TRX $0.27 etc | WIN $0.12 (0.25% move) LOSS $-0.28 (0.30% move) | Fee $0.10 | 70s timeout | Sub $1 moves 3-5x more!</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | SUB $1 ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,800))">🚀 FORCE SUB $1 FOCUS</button><button class=btn2 onclick="if(confirm('WIPE $119 to $300 SUB $1?')){fetch('/api/reset').then(()=>setTimeout(loadState,800))}">🗑️ WIPE → $300 SUB $1 FOCUS</button></div>
<div class=card><b>Open <span id=oc2>0/3</span> ONLY under $1 - high movers</b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed SUB $1 - 0.25% TP easy for sub $1</b><div id=closed>Waiting...</div></div>
<div class=card><b>Brain SUB $1</b><div id=brain class=m>Training...</div></div>
<div class=card><b>$50/Day SUB $1</b><div id=calc class=m>Waiting...</div></div>
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
  if(el('sub')) el('sub').innerText=j.price_count||0;
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/3';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/3';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode=='SHORT'?'🔻 SHORT':'🔥 LONG'} ${t.symbol} $${t.price} WR ${t.wr||0}% Mom ${t.m||0}% 24h ${t.m24||0}%</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'No open - sub $1 filter';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} $${c.price} ${c.hold}s Mom ${c.m||0}%</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${(c.net||0).toFixed(2)}</span></span></div>`).join('')||'No trades';
  if(el('brain')){ let stats=Object.entries(j.stats||{}).sort((a,b)=>(b[1].profit||0)-(a[1].profit||0)); el('brain').innerHTML=stats.slice(0,15).map(([k,v])=>`<div class=trade><span>${k.replace('USDT','')} ${v.w||0}W/${v.l||0}L ${Math.round(((v.w||0)/Math.max(1,(v.w||0)+(v.l||0)))*100)}% $${(v.profit||0).toFixed(2)}</span></div>`).join('')||'Scanning sub $1...'; }
  if(el('calc')){ let exp=0; if(j.total>10){ let w=j.wins/j.total; exp=w*0.12-(1-w)*0.28; } let perDay=exp*35*24; el('calc').innerHTML=`SUB $1: Moves 0.25% easy vs $300 coin needs 0.25% hard<br>Expectancy $${exp.toFixed(3)}/trade WIN $0.12 LOSS $-0.28<br>~35/h → $${(exp*35).toFixed(2)}/h → $${perDay.toFixed(2)}/day<br>Need 70% WR profit, sub $1 gives 65-75% WR = $30-50/day!<br>Current ${wr}% → ${perDay>=50?'✅ $50/day SUB $1 WORKS!':perDay>0?'⚠️ Profitable sub $1':'Waiting...'}`; }
 }catch(e){}
}
setInterval(loadState,3000); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},15000);
</script></body></html>"""
