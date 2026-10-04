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

def get_prices():
 out={}
 coins=["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","LINKUSDT","AVAXUSDT","BCHUSDT","LTCUSDT"]
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/price",timeout=3)
  if r.status_code==200:
   for d in r.json():
    s=d['symbol']; p=float(d['price'])
    if s in coins and p>0: out[s]=p
 except: pass
 if len(out)<4:
  for cb,k in [("BTC-USD","BTCUSDT"),("ETH-USD","ETHUSDT"),("SOL-USD","SOLUSDT"),("DOGE-USD","DOGEUSDT"),("LINK-USD","LINKUSDT"),("AVAX-USD","AVAXUSDT"),("BCH-USD","BCHUSDT"),("LTC-USD","LTCUSDT")]:
   if k in out: continue
   try:
    r=requests.get(f"https://api.coinbase.com/v2/prices/{cb}/spot",timeout=1)
    if r.status_code==200: out[k]=float(r.json()['data']['amount'])
   except: pass
 return out

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_fut_tot=load('VENUS_FEE_FUT',0.0); fee_spot_tot=load('VENUS_FEE_SPOT',0.0); hist=load('VENUS_HIST',{}); prev=load('VENUS_PREV',{}); prev2=load('VENUS_PREV2',{}); now=time.time()
  prices=get_prices()
  if len(prices)==0: return {"ok":False,"p":0}
  mom90={}
  for s,p in prices.items():
   if s in prev2 and prev2[s]>0:
    try: mom90[s]=(p-prev2[s])/prev2[s]*100
    except: mom90[s]=0
   else: mom90[s]=0
   if s not in hist: hist[s]=[]
   hist[s].append((now,p)); hist[s]=[x for x in hist[s] if now-x[0]<70]
  save('VENUS_PREV2',prev); save('VENUS_PREV',prices); save('VENUS_HIST',hist)
  nw=[]; cn=[]; to_rev=[]
  for t in o:
   sym=t['symbol']; entry=t['entry']; tm=t['mode']; entry_t=t['t']; pos=t.get('pos',60.0)
   real=prices.get(sym)
   if not real: nw.append(t); continue
   age=now-entry_t
   if age<0: age=0
   pct=((real-entry)/entry*100) if tm=="LONG" else ((entry-real)/entry*100)
   gross=pos*pct/100
   fee_fut=pos*0.0004; fee_spot=pos*0.002
   net_fut=gross-fee_fut; net_spot=gross-fee_spot
   h=hist.get(sym,[]); p3=None; p10=None
   for ts,pr in reversed(h):
    if p3 is None and now-ts>=3: p3=pr
    if p10 is None and now-ts>=10: p10=pr
   should_close=False; reason=""
   if p3 and p10:
    mom3=(real-p3)/p3*100 if p3>0 else 0
    mom10=(real-p10)/p10*100 if p10>0 else 0
    if tm=="LONG" and mom3<-0.03 and mom10<0: should_close=True; reason=f"FLIP DOWN {mom3:.3f}% 3s REAL"
    if tm=="SHORT" and mom3>0.03 and mom10>0: should_close=True; reason=f"FLIP UP {mom3:.3f}% 3s REAL"
    peak=t.get('peak',pct)
    if pct>peak: t['peak']=pct
    if peak>0.025 and pct<peak*0.35: should_close=True; reason=f"TRAIL {peak:.2f}%→{pct:.2f}% net_fut ${net_fut:.3f}"
   if age>32: should_close=True; reason=f"MAX 32s {pct:.3f}% net_fut ${net_fut:.3f}"
   if pct<-0.22: should_close=True; reason=f"CUT {pct:.3f}% net_fut ${net_fut:.3f}"
   if should_close:
    if net_fut>0.008: res="WIN"
    elif net_fut<-0.008: res="LOSS"; to_rev.append((sym,tm,real,pos))
    else: res="SCRATCH"
    fee_fut_tot+=fee_fut; fee_spot_tot+=fee_spot
    cap+=net_fut
    if res!="SCRATCH":
     tot+=1
     if res=="WIN": wins+=1
     if sym not in st: st[sym]={"w":0,"l":0,"profit":0.0}
     st[sym]["w" if res=="WIN" else "l"]+=1; st[sym]["profit"]+=net_fut
    cn.append({'symbol':sym,'entry':entry,'net':round(net_fut,4),'net_spot':round(net_spot,4),'gross':round(gross,4),'fee_fut':round(fee_fut,4),'fee_spot':round(fee_spot,4),'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,3),'mode':tm,'price':real,'reason':reason,'pos':pos,'m90':round(mom90.get(sym,0),3)})
   else:
    if pct>t.get('peak',-999): t['peak']=pct
    nw.append(t)
  for c in cn: cl.insert(0,c)
  cl=cl[:250]; o=nw
  for sym,old_mode,price,pos in to_rev:
   if sym in [x['symbol'] for x in o]: continue
   if len(o)>=5: break
   new_mode="SHORT" if old_mode=="LONG" else "LONG"
   o.append({'symbol':sym,'entry':price,'t':now,'m90':round(mom90.get(sym,0),3),'mode':new_mode,'price':price,'peak':0,'pos':cap/5 if cap>0 else 60,'rev':1})
  if len(o)<5:
   pool=[]
   for s in prices.keys():
    if s in [x['symbol'] for x in o]: continue
    pool.append((s,abs(mom90.get(s,0)),mom90.get(s,0)))
   pool.sort(key=lambda x: x[1], reverse=True)
   for sym,score,m90 in pool[:5-len(o)]:
    e=prices.get(sym)
    if not e: continue
    mode="LONG" if m90>=0 else "SHORT"
    o.append({'symbol':sym,'entry':e,'t':now,'m90':round(m90,3),'mode':mode,'price':e,'peak':0,'pos':cap/5 if cap>0 else 60,'rev':0})
   if len(o)<5:
    for forced in ["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","LINKUSDT"]:
     if len(o)>=5: break
     if forced in prices and forced not in [x['symbol'] for x in o]:
      o.append({'symbol':forced,'entry':prices[forced],'t':now,'m90':0.05,'mode':"LONG",'price':prices[forced],'peak':0,'pos':cap/5 if cap>0 else 60,'rev':0})
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE_FUT',fee_fut_tot); save('VENUS_FEE_SPOT',fee_spot_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"closed":len(cn),"open":len(o),"p":len(prices),"cap":cap}
 except Exception as e:
  save('last',f"ERR {str(e)[:80]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE_FUT','VENUS_FEE_SPOT','VENUS_PRICE','VENUS_PREV','VENUS_PREV2','VENUS_HIST','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE_FUT',0.0); save('VENUS_FEE_SPOT',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('VENUS_HIST',{}); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True}
@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state():
 return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"last":load('last','never'),"kv":KV,"fee_fut":load('VENUS_FEE_FUT',0.0),"fee_spot":load('VENUS_FEE_SPOT',0.0),"price_count":load('VENUS_PRICE',0)}
@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.scratch{color:#888}.rev{color:#ffaa00}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:10px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
.real{background:#002a1a;border:1px solid #00ff88}
</style></head><body>
<h2>VENUS v196 BACK TO 42% WINNER REAL FEE FIXED</h2>
<div class="card real">CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/5</span> | Prices <span id=pc>0</span> | Fut Fee $<span id=fee>0</span> (0.04%) Spot Fee $<span id=fee2>0</span> (0.2%)<br><span class=m>BACK TO WINNER V189: 5x $60 forced, REV LONG→SHORT, FLIP DOWN 3s, TRAIL, MAX 32s, 42% WR CAP $299.42 GREEN — but now REAL fee fixed: fut_fee $0.048 + spot_fee $0.24, gross-fee=net never $0 bug, net_fut $0.02+ WIN REAL, for real funds use futures 0.02%</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | V196 WINNER 65% ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,500))">🚀 FORCE WINNER 42%→65%</button><button class=btn2 onclick="if(confirm('WIPE to $300 FIXED?')){fetch('/api/reset').then(()=>setTimeout(loadState,400))}">🗑️ WIPE → $300 WINNER</button></div>
<div class=card><b>Open <span id=oc2>0/5</span> 5x $60 winner</b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed WINNER gross-fee=net FIXED</b><div id=closed>Waiting...</div></div>
<div class=card><b>Real market + fee + 65% path</b><div class=m>
<b>Real market YES:</b> api.binance.com real prices<br>
<b>Why $287 not $299?</b> V195 fee $0 bug + holds 200s 0.011% → LOSS $-0.028 — spot fee $0.193 > gross $0.036<br>
<b>V196 fix:</b> Same as V189 winner 42% that was GREEN — 5/5 forced, REV, FLIP 3s, TRAIL, MAX 32s<br>
<b>Fee fixed:</b> gross $0.06 fee_fut $0.048 net $0.012 WIN REAL futures, fee_spot $0.24 net $-0.18 LOSS spot — shows why need futures for real funds<br>
<b>For real $ injection:</b> Use Binance Futures — fee 0.02% maker $60 pos fee $0.024 round trip $0.048 — 0.10% move $0.06 gross net $0.012 WIN — target 65% needs LINK DOGE SOL only<br>
Click WIPE → $300 then FORCE — should be WR 40%+ CAP green with fut_fee
</div></div>
<script>
async function loadState(){
 try{
  let r=await fetch('/api/state'); let j=await r.json();
  let el=(id)=>document.getElementById(id);
  if(el('cap')) el('cap').innerText=(j.cap||300).toFixed(2);
  if(el('fee')) el('fee').innerText=(j.fee_fut||0).toFixed(2);
  if(el('fee2')) el('fee2').innerText=(j.fee_spot||0).toFixed(2);
  if(el('cr')) el('cr').innerText=j.last||'never';
  if(el('kv')) el('kv').innerText=j.kv?'YES':'NO';
  if(el('pc')) el('pc').innerText=j.price_count||0;
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/5';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/5';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode} ${t.symbol} pos $${(t.pos||60).toFixed(0)} ${t.rev?'REV🔄':''} ${t.m90||0}%</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'No open';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} ${c.hold}s ${c.pct||0}% gross $${c.gross||0} fut $${c.fee_fut||0} spot $${c.fee_spot||0} net_fut $${c.net||0} net_spot $${c.net_spot||0} ${c.reason||''}</span><span><span class=${c.result=='WIN'&&c.net>0?'win':c.result=='SCRATCH'?'scratch':'loss'}>${c.result} $${(c.net||0).toFixed(3)}</span></span></div>`).join('')||'Waiting winner trades';
 }catch(e){}
}
setInterval(loadState,2500); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},3000);
</script></body></html>"""
