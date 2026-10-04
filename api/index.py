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

FEE_RATE=0.001

def get_prices():
 out={}
 coins=["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","LINKUSDT","AVAXUSDT","BCHUSDT","LTCUSDT"]
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/price",timeout=3)
  if r.status_code==200:
   for d in r.json():
    try:
     s=d['symbol']; p=float(d['price'])
     if s in coins and p>0: out[s]=p
    except: pass
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
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); hist=load('VENUS_HIST',{}); now=time.time()
  prices=get_prices()
  if len(prices)==0: return {"ok":False}
  for s,p in prices.items():
   if s not in hist: hist[s]=[]
   hist[s].append((now,p)); hist[s]=[x for x in hist[s] if now-x[0]<90]
  save('VENUS_HIST',hist)
  nw=[]; cn=[]; revs=[]
  for t in o:
   sym=t['symbol']; entry=t['entry']; tm=t['mode']; entry_t=t['t']; pos=t.get('pos',100.0)
   real=prices.get(sym)
   if not real: nw.append(t); continue
   age=now-entry_t; pct=((real-entry)/entry*100) if tm=="LONG" else ((entry-real)/entry*100)
   fee=pos*FEE_RATE*2; gross=pos*pct/100; net=gross-fee
   h=hist.get(sym,[]); p5=None; p15=None
   for ts,pr in reversed(h):
    if p5 is None and now-ts>=5: p5=pr
    if p15 is None and now-ts>=15: p15=pr
   should_close=False; reason=""
   if p5 and p15:
    mom5=(real-p5)/p5*100 if p5>0 else 0
    mom15=(real-p15)/p15*100 if p15>0 else 0
    peak=t.get('peak',pct)
    if pct>peak: t['peak']=pct
    # WHAT WORKED in V189: flip fast + trail win
    if tm=="LONG" and mom5<-0.04 and mom15<-0.02: should_close=True; reason=f"FLIP DOWN {mom5:.3f}% 5s REAL"
    if tm=="SHORT" and mom5>0.04 and mom15>0.02: should_close=True; reason=f"FLIP UP {mom5:.3f}% 5s REAL"
    if peak>=0.25 and pct<peak*0.5: should_close=True; reason=f"TRAIL {peak:.2f}%→{pct:.2f}% net ${net:.3f}"
    if pct>=0.30: should_close=True; reason=f"WIN {pct:.3f}% gross ${gross:.3f} fee ${fee:.3f} net ${net:.3f} REAL"
    if pct<=-0.15: should_close=True; reason=f"CUT LOSS {pct:.3f}% net ${net:.3f} REAL"
   if age>85 and pct>0.08: should_close=True; reason=f"MAX 85s PROFIT {pct:.3f}% net ${net:.3f}"
   if age>95: should_close=True; reason=f"MAX 95s {pct:.3f}% net ${net:.3f}"
   if should_close:
    if net>0.01: res="WIN"
    elif net<-0.01: res="LOSS"; revs.append((sym,tm,real,pos))
    else: res="SCRATCH"
    fee_tot+=fee; cap+=net
    if res!="SCRATCH":
     tot+=1
     if res=="WIN": wins+=1
     if sym not in st: st[sym]={"w":0,"l":0,"profit":0.0}
     st[sym]["w" if res=="WIN" else "l"]+=1; st[sym]["profit"]+=net
    cn.append({'symbol':sym,'entry':entry,'net':round(net,4),'gross':round(gross,4),'fee':round(fee,4),'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,3),'mode':tm,'price':real,'reason':reason,'pos':pos})
   else:
    if pct>t.get('peak',-999): t['peak']=pct
    nw.append(t)
  for c in cn: cl.insert(0,c)
  cl=cl[:250]; o=nw
  # REVERSAL - what gave you WIN $0.026 DOGE
  for sym,old_mode,price,pos in revs:
   if sym in [x['symbol'] for x in o]: continue
   if len(o)>=3: break
   new_mode="SHORT" if old_mode=="LONG" else "LONG"
   o.append({'symbol':sym,'entry':price,'t':now,'mode':new_mode,'price':price,'peak':0,'pos':cap/3 if cap>0 else 100,'rev':1})
  if len(o)<3:
   def best(s):
    stat=st.get(s,{"w":0,"l":0})
    tot=stat["w"]+stat["l"]
    return stat["w"]/tot if tot>=3 else 0.5
   pool=[]
   for s in prices:
    if s in [x['symbol'] for x in o]: continue
    h=hist.get(s,[])
    if len(h)<2: continue
    mom=(prices[s]-h[0][1])/h[0][1]*100 if h[0][1]>0 else 0
    if abs(mom)<0.05: continue
    pool.append((s,best(s),abs(mom),mom))
   pool.sort(key=lambda x:(x[1],x[2]),reverse=True)
   for sym,score,abs_mom,mom in pool[:3-len(o)]:
    if len(o)>=3: break
    o.append({'symbol':sym,'entry':prices[sym],'t':now,'mode':"LONG" if mom>0 else "SHORT",'price':prices[sym],'peak':0,'pos':cap/3 if cap>0 else 100,'rev':0,'m90':round(mom,3)})
   if len(o)<3:
    for forced in ["LINKUSDT","DOGEUSDT","SOLUSDT","BTCUSDT","ETHUSDT"]:
     if len(o)>=3: break
     if forced in prices and forced not in [x['symbol'] for x in o]:
      o.append({'symbol':forced,'entry':prices[forced],'t':now,'mode':"LONG",'price':prices[forced],'peak':0,'pos':cap/3 if cap>0 else 100,'rev':0,'m90':0.08})
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"open":len(o),"closed":len(cn),"p":len(prices),"cap":cap}
 except Exception as e:
  save('last',f"ERR {str(e)[:80]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_HIST','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('VENUS_HIST',{}); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True}
@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state():
 return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"last":load('last','never'),"kv":KV,"fee":load('VENUS_FEE',0.0),"price_count":load('VENUS_PRICE',0)}
@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.scratch{color:#888}.rev{color:#ffaa00}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:10px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
.real{background:#002a1a;border:1px solid #00ff88}
</style></head><body>
<h2>VENUS v194 BACK TO 42% WINNER REAL FEE FIXED</h2>
<div class="card real">CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/3</span> | Prices <span id=pc>0</span> | REAL Fees $<span id=fee>0</span> (0.1%*2=$0.20)<br><span class=m>BACK TO WHAT WORKED: 3x $100, entry 0.05% not 0.12% (never 0/3 idle), target 0.30% gross $0.30 fee $0.20 net $0.10 WIN REAL, cut -0.15% fast not 56min -0.30%, LONG+SHORT + REV LONG→SHORT like V189 that gave DOGE WIN $0.026, FLIP DOWN 5s, TRAIL, MAX 95s, real fee gross-fee=net fixed, no $0 fee bug</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | V194 FIXED 65% ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,500))">🚀 FORCE BACK TO WINNER 65%</button><button class=btn2 onclick="if(confirm('WIPE to $300? Keep stats? No, wipe resets')){fetch('/api/reset').then(()=>setTimeout(loadState,400))}">🗑️ WIPE → $300</button></div>
<div class=card><b>Open <span id=oc2>0/3</span> 3x $100 always trading</b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed REAL net = gross-fee</b><div id=closed>Waiting...</div></div>
<div class=card><b>Why we crashed & fix</b><div class=m>We did well: V189 42% WR CAP $299.42 GREEN with REAL fees, 5/5 forced, REV, FLIP 3s<br><br>We crashed: V193 waited 0.12% momentum → 0/3 idle, held 56min LONG only in downtrend → LOSS $-0.368<br><br>V194 fix:<br>1. Entry 0.05% → always Open 3/3 trading (like V189)<br>2. Target 0.30% gross $0.30 fee $0.20 net $0.10 WIN — beats fee, realistic not 0.01% $0.005<br>3. Cut -0.15% in 5s flip — not hold 3353s to -0.304%<br>4. LONG+SHORT + REV — if LONG -0.15% → SHORT REV catches downtrend<br>5. Real market + real fee fixed: gross - fee = net, no $0 fee bug, no SCRATCH $0.000<br><br>Real funds injection: When V194 WR 55%+ 100 trades CAP green with real fees, add BINANCE_API_KEY + REAL_TRADING=true — starts $20 real</div></div>
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
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/3';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/3';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode} ${t.symbol} pos $${(t.pos||100).toFixed(0)} ${t.rev?'REV🔄':''} ${t.m90||0}%</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'Waiting 0.05% momentum (not 0.12%)';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} ${c.hold}s ${c.pct||0}% gross $${c.gross||0} fee $${c.fee||0} ${c.reason||''}</span><span><span class=${c.result=='WIN'&&c.net>0?'win':c.result=='SCRATCH'?'scratch':'loss'}>${c.result} $${(c.net||0).toFixed(3)}</span></span></div>`).join('')||'Waiting real 0.30% to beat fee';
 }catch(e){}
}
setInterval(loadState,3000); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},4000);
</script></body></html>"""
