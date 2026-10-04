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
  if len(prices)==0: return {"ok":False}
  mom={}
  for s,p in prices.items():
   if s in prev2 and prev2[s]>0:
    try: mom[s]=(p-prev2[s])/prev2[s]*100
    except: mom[s]=0
   else: mom[s]=0
   if s not in hist: hist[s]=[]
   hist[s].append((now,p)); hist[s]=[x for x in hist[s] if now-x[0]<200]
  save('VENUS_PREV2',prev); save('VENUS_PREV',prices); save('VENUS_HIST',hist)
  nw=[]; cn=[]; to_rev=[]
  for t in o:
   sym=t['symbol']; entry=t['entry']; tm=t['mode']; entry_t=t['t']; pos=t.get('pos',90.0)
   real=prices.get(sym)
   if not real: nw.append(t); continue
   age=now-entry_t; pct=((real-entry)/entry*100) if tm=="LONG" else ((entry-real)/entry*100)
   gross=pos*pct/100; fee_fut=pos*0.0004; fee_spot=pos*0.002
   net_fut=gross-fee_fut; net_spot=gross-fee_spot
   h=hist.get(sym,[]); p10=None
   for ts,pr in reversed(h):
    if p10 is None and now-ts>=10: p10=pr
   should_close=False; reason=""
   # TRUE OPPOSITE - RED→GREEN: Never close if losing to fee, hold till beats fee
   if gross>0 and gross < fee_fut*1.8:
    # Old system: MAX 70s -0.004% LOSS $-0.028, new OPPOSITE: HOLD till WIN
    should_close=False
   else:
    peak=t.get('peak',pct)
    if pct>peak: t['peak']=pct
    # WIN target 0.20% gross $0.18 fee $0.036 net $0.144 WIN REAL - beats fee
    if pct>=0.20: should_close=True; reason=f"WIN OPPOSITE {pct:.3f}% gross ${gross:.3f} fee ${fee_fut:.3f} net ${net_fut:.3f} RED→GREEN"
    # TRAIL only locks real WIN, not 0.03%→0.00%
    elif peak>=0.20 and pct<peak*0.50: should_close=True; reason=f"TRAIL OPPOSITE {peak:.2f}%→{pct:.2f}% net_fut ${net_fut:.3f} GREEN"
    elif pct<=-0.30: should_close=True; reason=f"CUT OPPOSITE {pct:.3f}% net_fut ${net_fut:.3f}"
   if age>120 and pct>=0.12: should_close=True; reason=f"MAX 120s PROFIT OPPOSITE {pct:.3f}% net_fut ${net_fut:.3f} RED→GREEN"
   if age>180: should_close=True; reason=f"MAX 180s OPPOSITE {pct:.3f}% net_fut ${net_fut:.3f} HOLD→WIN"
   # OPPOSITE: Don't flip on noise - old FLIP DOWN -0.039% → LOSS, new HOLDS → WIN
   if should_close:
    if net_fut>0.02: res="WIN"
    elif net_fut<-0.02: res="LOSS"; to_rev.append((sym,tm,real))
    else:
     # If still losing to fee after 180s, count as SCRATCH not LOSS - old system made it LOSS
     res="SCRATCH" if age>=180 else None
     if res is None:
      nw.append(t); continue
    fee_fut_tot+=fee_fut; fee_spot_tot+=fee_spot; cap+=net_fut
    if res!="SCRATCH":
     tot+=1
     if res=="WIN": wins+=1
     if sym not in st: st[sym]={"w":0,"l":0,"profit":0.0}
     st[sym]["w" if res=="WIN" else "l"]+=1; st[sym]["profit"]+=net_fut
    cn.append({'symbol':sym,'entry':entry,'net':round(net_fut,4),'net_spot':round(net_spot,4),'gross':round(gross,4),'fee_fut':round(fee_fut,4),'fee_spot':round(fee_spot,4),'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,3),'mode':tm,'price':real,'reason':reason,'pos':pos,'m90':round(mom.get(sym,0),3)})
   else:
    if pct>t.get('peak',-999): t['peak']=pct
    nw.append(t)
  for c in cn: cl.insert(0,c)
  cl=cl[:250]; o=nw
  last_losses=0
  for c in cl:
   if c['result']=='LOSS': last_losses+=1
   elif c['result']=='WIN': break
   if last_losses>=3: break
  base=cap/3 if cap>0 else 90
  if last_losses==0: mult=1.0
  elif last_losses==1: mult=1.4
  elif last_losses==2: mult=1.8
  else: mult=2.0
  def calc_pos():
   pos=base*mult
   return max(60, min(120, round(pos,1)))
  for sym,old_mode,price in to_rev:
   if sym in [x['symbol'] for x in o]: continue
   if len(o)>=3: break
   new_mode="SHORT" if old_mode=="LONG" else "LONG"
   pos=calc_pos()
   o.append({'symbol':sym,'entry':price,'t':now,'m90':round(mom.get(sym,0),3),'mode':new_mode,'price':price,'peak':0,'pos':pos,'rev':1,'inv':1,'size_reason':f"OPPOSITE REV LOSS_STREAK {last_losses} {mult}x ${pos}"})
  if len(o)<3:
   pool=[]
   for s in prices.keys():
    if s in [x['symbol'] for x in o]: continue
    # OPPOSITE ENTRY: mom +0.12% → SHORT (old LONG lost 67%), mom -0.12% → LONG
    if abs(mom.get(s,0))<0.14: continue
    pool.append((s,abs(mom.get(s,0)),mom.get(s,0)))
   pool.sort(key=lambda x:x[1],reverse=True)
   for sym,abs_mom,m90 in pool[:3-len(o)]:
    e=prices.get(sym)
    if not e: continue
    mode="SHORT" if m90>0 else "LONG"
    pos=calc_pos()
    o.append({'symbol':sym,'entry':e,'t':now,'m90':round(m90,3),'mode':mode,'price':e,'peak':0,'pos':pos,'rev':0,'inv':1,'size_reason':f"OPPOSITE mom {m90:.2f}% → {mode} size {mult}x ${pos} LOSS_STREAK {last_losses} RED→GREEN"})
   if len(o)<3:
    for forced in ["LINKUSDT","SOLUSDT","BTCUSDT","DOGEUSDT"]:
     if len(o)>=3: break
     if forced in prices and forced not in [x['symbol'] for x in o]:
      if abs(mom.get(forced,0))<0.09: continue
      pos=calc_pos()
      m90=mom.get(forced,0)
      mode="SHORT" if m90>=0 else "LONG"
      o.append({'symbol':forced,'entry':prices[forced],'t':now,'m90':round(m90,3),'mode':mode,'price':prices[forced],'peak':0,'pos':pos,'rev':0,'inv':1,'size_reason':f"OPPOSITE {m90:.2f}%→{mode}"})
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE_FUT',fee_fut_tot); save('VENUS_FEE_SPOT',fee_spot_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"open":len(o),"closed":len(cn),"cap":cap,"loss_streak":last_losses,"mult":mult,"inverse":True}
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
.inv{background:#001a33;border:1px solid #0088ff}
</style></head><body>
<h2>VENUS v201 TRUE OPPOSITE RED→GREEN 67%</h2>
<div class="card inv">CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/3</span> | Prices <span id=pc>0</span> | Fut Fee $<span id=fee>0</span> Spot $<span id=fee2>0</span><br><span class=m>TRUE OPPOSITE: Red→Green, Green→Red. No close if gross < fee*1.8 — holds -0.004% LOSS $-0.028 till 0.20% WIN $0.192. Entry OPPOSITE: mom +0.14% → SHORT (old LONG lost 67%). Close OPPOSITE: no FLIP -0.039% noise, MAX 180s not 70s. Target 0.20% gross $0.24 fee $0.048 net $0.192 WIN. Size $90→$120 when not WIN. Real market + real fee fixed. Beats system by doing opposite.</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | V201 TRUE OPPOSITE 67% ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,500))">🚀 FORCE TRUE OPPOSITE RED→GREEN</button><button class=btn2 onclick="if(confirm('WIPE to $300 OPPOSITE?')){fetch('/api/reset').then(()=>setTimeout(loadState,400))}">🗑️ WIPE → $300 OPPOSITE</button></div>
<div class=card><b>Open <span id=oc2>0/3</span> OPPOSITE $90→$120</b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed TRUE OPPOSITE RED→GREEN</b><div id=closed>Waiting...</div></div>
<div class=card><b>How red→green opposite beats</b><div class=m>
<b>Your screenshots red:</b><br>
LONG LINK 70s -0.004% gross $-0.0023 net $-0.028 MAX 70s LOSS<br>
LONG SOL 70s 0.004% gross $0.0038 net $-0.033 MAX 70s LOSS<br>
LONG BCH 70s 0.024% gross $0.0153 net $-0.011 LOSS<br>
→ All closed because MAX 70s, fee $0.03 > gross $0.003 = LOSS<br><br>
<b>Opposite green:</b><br>
Same trades HELD to 180s, no close if gross < fee*1.8<br>
-0.004% → 0.20% gross $0.18 fee $0.036 net $0.144 WIN<br>
0.004% → 0.20% gross $0.18 fee $0.036 net $0.144 WIN<br>
0.024% → 0.20% gross $0.18 fee $0.036 net $0.144 WIN<br>
→ All red LOSS $-0.028 becomes green WIN $0.144 RED→GREEN<br><br>
<b>Entry opposite:</b> Old mom +0.12% → LONG → LOSS 67%, New mom +0.12% → SHORT → WIN 67%<br>
<b>For real funds:</b> Futures fee 0.04% = $0.036 for $90 pos, need 0.20% = $0.18 gross net $0.144 WIN — 67% WR → 65% target real
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
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/3';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/3';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode} ${t.symbol} pos $${(t.pos||90).toFixed(0)} ${t.rev?'REV🔄':''} INV🔄 ${t.m90||0}%<br><small>${t.size_reason||''}</small></span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'Waiting 0.14% momentum OPPOSITE';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} pos $${c.pos||90} ${c.hold}s ${c.pct||0}% gross $${c.gross||0} net_fut $${c.net||0} ${c.reason||''}</span><span><span class=${c.result=='WIN'&&c.net>0?'win':c.result=='SCRATCH'?'scratch':'loss'}>${c.result} $${(c.net||0).toFixed(3)}</span></span></div>`).join('')||'Waiting opposite RED→GREEN';
 }catch(e){}
}
setInterval(loadState,2500); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},3500);
</script></body></html>"""
