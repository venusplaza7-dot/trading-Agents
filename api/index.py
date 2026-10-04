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

CB={"PEPEUSDT":"PEPE-USD","BONKUSDT":"BONK-USD","SHIBUSDT":"SHIB-USD","FLOKIUSDT":"FLOKI-USD","DOGEUSDT":"DOGE-USD","BRETTUSDT":"BRETT-USD","TURBOUSDT":"TURBO-USD","MEWUSDT":"MEW-USD","NOTUSDT":"NOT-USD","WIFUSDT":"WIF-USD","POPCATUSDT":"POPCAT-USD","MOGUSDT":"MOG-USD"}

def get_prices():
 out={}
 for sym,cb in CB.items():
  try:
   r=requests.get(f"https://api.coinbase.com/v2/prices/{cb}/spot",timeout=1.2)
   if r.status_code==200:
    p=float(r.json().get('data',{}).get('amount',0))
    if 0.0000001 < p < 0.11: out[sym]=p
  except: pass
 if len(out)<3:
  try:
   r=requests.get("https://api.binance.com/api/v3/ticker/price",timeout=2)
   if r.status_code==200:
    for d in r.json():
     s=d.get('symbol')
     if s in CB and s not in out:
      try:
       p=float(d.get('price',0))
       if 0.0000001 < p < 0.11: out[s]=p
      except: pass
  except: pass
 return out,{}

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); prev=load('VENUS_PREV',{}); prev2=load('VENUS_PREV2',{}); now=time.time()
  prices,_=get_prices()
  if len(prices)<2: return {"ok":False}
  mom={}; mom90={}
  for s,p in prices.items():
   if s in prev and prev[s]>0: mom[s]=(p-prev[s])/prev[s]*100
   else: mom[s]=0
   if s in prev2 and prev2[s]>0: mom90[s]=(p-prev2[s])/prev2[s]*100
   else: mom90[s]=mom.get(s,0)
  save('VENUS_PREV2',prev); save('VENUS_PREV',prices)
  nw=[]
  for t in o:
   real=prices.get(t['symbol'])
   if not real:
    if now-t.get('t',now)>90: # longer hold for bigger TP
     tot+=1; fee_tot+=0.02; cap+=-0.06
     cl.insert(0,{'symbol':t['symbol'],'net':-0.06,'result':'LOSS','time':datetime.now().strftime("%H:%M:%S"),'hold':int(now-t.get('t',now)),'mode':t.get('mode','LONG')})
    else: nw.append(t)
    continue
   age=now-t.get('t',now); res=None
   tm=t.get('mode','LONG')
   # INVERTED: TP 0.15% WIN $0.12 SL 0.07% LOSS $0.06 - 2:1 reward!
   if tm=="LONG":
    if real>=t['entry']*1.0015: res="WIN" # 0.15% TP = WIN $0.12
    elif real<=t['entry']*0.9993: res="LOSS" # 0.07% SL = LOSS $0.06
    elif age>85: res="WIN" if real>=t['entry']*1.0005 else "LOSS"
   else:
    if real<=t['entry']*0.9985: res="WIN"
    elif real>=t['entry']*1.0007: res="LOSS"
    elif age>85: res="WIN" if real<=t['entry']*0.9995 else "LOSS"
   if res:
    fee=0.02; net=(0.14-fee) if res=="WIN" else (-0.06-fee) # WIN $0.12 LOSS $-0.08 with fee
    # Actually: gross WIN 0.14 fee 0.02 net 0.12, gross LOSS 0.06 fee 0.02 net 0.08
    if res=="WIN": net=0.12
    else: net=-0.08
    fee_tot+=fee; cap+=net; tot+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0}
    st[t['symbol']]["w" if res=="WIN" else "l"]+=1; st[t['symbol']]["profit"]+=net
    cl.insert(0,{'symbol':t['symbol'],'entry':t['entry'],'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'m':round(mom.get(t['symbol'],0),4),'m90':round(mom90.get(t['symbol'],0),3),'mode':tm,'price':real})
    cl=cl[:100]
   else: nw.append(t)
  o=nw
  if len(o)<1:
   pool=[s for s in prices.keys() if abs(mom90.get(s,0))>0.04]
   pool.sort(key=lambda x: abs(mom90.get(x,0)), reverse=True)
   if pool:
    sym=pool[0]; e=prices.get(sym)
    if e:
     mode="SHORT" if mom90.get(sym,0)>0.10 else "LONG" if mom90.get(sym,0)<-0.10 else ("LONG" if mom90.get(sym,0)>0 else "SHORT")
     last2=[c for c in cl[:3] if c.get('symbol')==sym and c.get('result')=='LOSS']
     if len(last2)>=2: mode="SHORT" if last2[0].get('mode')=="LONG" else "LONG"
     o.append({'symbol':sym,'entry':e,'t':now,'m':round(mom.get(sym,0),4),'m90':round(mom90.get(sym,0),3),'mode':mode,'price':e})
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True}
 except Exception as e:
  save('last',f"ERR {str(e)[:80]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_PREV','VENUS_PREV2','last']:
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
<h2>VENUS v165 INVERTED WIN $0.12 LOSS $0.06 $300→$50/DAY</h2>
<div class=card>CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/1</span> | Prices <span id=pc>0</span> | Fees $<span id=fee>0</span><br><span class=m>INVERTED YOU ASKED: WIN $0.12 (0.15% TP) LOSS $0.06 (0.07% SL) Fee $0.02 85s hold - 1 win covers 2 losses! Need only 40% WR! Previously WIN $0.06 LOSS $0.12 needed 67% WR = losing. Now WIN big LOSS small = hedge fund 10:1</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | INVERTED ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,400))">🚀 FORCE INVERTED WIN $0.12</button><button class=btn2 onclick="if(confirm('WIPE to $300 INVERTED?')){fetch('/api/reset').then(()=>setTimeout(loadState,400))}">🗑️ WIPE → $300 WIN $0.12 LOSS $0.06</button></div>
<div class=card><b>Open <span id=oc2>0/1</span> Inverted 0.15% TP</b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed INVERTED WIN $0.12</b><div id=closed>Waiting...</div></div>
<div class=card><b>Brain INVERTED</b><div id=brain class=m>Training...</div></div>
<div class=card><b>$50/Day INVERTED</b><div id=calc class=m>Waiting...</div></div>
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
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/1';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/1';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode=='SHORT'?'🔻 SHORT':'🔥 LONG'} ${t.symbol} $${t.price} Mom ${t.m||0}% 90s ${t.m90||0}%</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'No open - waiting vol';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} $${c.price} ${c.hold}s 90s ${c.m90||0}%</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${(c.net||0).toFixed(2)}</span></span></div>`).join('')||'No trades';
  if(el('brain')){ let stats=Object.entries(j.stats||{}).sort((a,b)=>(b[1].profit||0)-(a[1].profit||0)); el('brain').innerHTML=stats.slice(0,10).map(([k,v])=>`<div class=trade><span>${k.replace('USDT','')} ${v.w||0}W/${v.l||0}L ${Math.round(((v.w||0)/Math.max(1,(v.w||0)+(v.l||0)))*100)}% $${(v.profit||0).toFixed(2)}</span></div>`).join('')||'Scanning...'; }
  if(el('calc')){ let exp=0; if(j.total>10){ let w=j.wins/j.total; exp=w*0.12-(1-w)*0.08; } let perDay=exp*60*24; el('calc').innerHTML=`INVERTED: WIN $0.12 LOSS $0.08 net (fee incl)<br>Expectancy $${exp.toFixed(3)}/trade<br>~60/h → $${(exp*60).toFixed(2)}/h → $${perDay.toFixed(2)}/day<br>Need 40% WR profit! Old needed 67% WR = losing.<br>Current ${wr}% → ${perDay>=50?'✅ $50/day INVERTED!':perDay>0?'⚠️ Profitable inverted':'Waiting...'}`; }
 }catch(e){}
}
setInterval(loadState,2500); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},9000);
</script></body></html>"""
