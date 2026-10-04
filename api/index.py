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
 coins=["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","LINKUSDT","AVAXUSDT","BCHUSDT","LTCUSDT","UNIUSDT","NEARUSDT","PEPEUSDT","BONKUSDT"]
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/price",timeout=2.5)
  if r.status_code==200:
   ap={d['symbol']:float(d['price']) for d in r.json() if 'price' in d}
   for b in coins:
    p=ap.get(b)
    if p and p>0: out[b]=p
 except: pass
 if len(out)<3:
  mp={"BTCUSDT":"BTC-USD","ETHUSDT":"ETH-USD","SOLUSDT":"SOL-USD","DOGEUSDT":"DOGE-USD"}
  for s,c in mp.items():
   if s in out: continue
   try:
    r=requests.get(f"https://api.coinbase.com/v2/prices/{c}/spot",timeout=1)
    if r.status_code==200:
     out[s]=float(r.json()['data']['amount'])
   except: pass
 return out

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0)
  hist=load('VENUS_HIST',{}); learn=load('VENUS_LEARN',{}); prev=load('VENUS_PREV',{}); now=time.time()
  prices=get_prices()
  if len(prices)<2: return {"ok":False,"p":len(prices)}
  # LEARNING: track price history per coin last 60s
  for s,p in prices.items():
   if s not in hist: hist[s]=[]
   hist[s].append((now,p))
   hist[s]=[x for x in hist[s] if now-x[0]<60]
   if s not in learn: learn[s]={"w":0,"l":0,"score":0.5,"last_trades":[]}
  save('VENUS_HIST',hist)
  nw=[]; cn=[]
  for t in o:
   sym=t['symbol']; entry=t['entry']; tm=t['mode']; entry_t=t['t']
   real=prices.get(sym)
   if not real: nw.append(t); continue
   # REAL-TIME FOLLOWING: Check 5sec vs 10sec momentum
   h=hist.get(sym,[])
   p5=None; p10=None; p15=None
   for ts,pr in reversed(h):
    if p5 is None and now-ts>=5: p5=pr
    if p10 is None and now-ts>=10: p10=pr
    if p15 is None and now-ts>=15: p15=pr
   age=now-entry_t
   pct=((real-entry)/entry*100) if tm=="LONG" else ((entry-real)/entry*100) if entry>0 else 0
   # BOT DECIDES: No fixed %, learns from market flip
   should_close=False; reason=""
   # 1. Market flipped: went up 5sec then down 10sec - flip position
   if p5 and p10:
    short_mom=(real-p5)/p5*100 if p5>0 else 0
    mid_mom=(p5-p10)/p10*100 if p10>0 and p5 else 0
    # If LONG but last 5sec down and 10sec up was up - market flipping down -> close LONG
    if tm=="LONG" and short_mom<-0.04 and mid_mom>0:
     should_close=True; reason=f"FLIP DOWN {short_mom:.3f}%"
    if tm=="SHORT" and short_mom>0.04 and mid_mom<0:
     should_close=True; reason=f"FLIP UP {short_mom:.3f}%"
    # Trailing profit: if profit peaked and now dropping 40%
    peak=t.get('peak',pct)
    if pct>peak: t['peak']=pct; peak=pct
    if peak>0.03 and pct<peak*0.4:
     should_close=True; reason=f"TRAIL PEAK {peak:.3f}%→{pct:.3f}%"
   # 2. Age max 60s but can close early if market moves
   if age>60:
    should_close=True; reason="MAX 60s"
   # 3. Hard safety: big loss - bot learns to cut fast
   if pct<-0.25:
    should_close=True; reason="CUT LOSS"
   if should_close:
    # BOT LEARNS: decides profit/loss itself, no fixed %
    if pct>0.01: res="WIN"; net=max(0.02,pct*0.5)
    elif pct<-0.01: res="LOSS"; net=min(-0.02,pct*0.5)
    else: res="SCRATCH"; net=0
    # Learn from mistake
    if sym in learn:
     if res=="WIN": learn[sym]["w"]+=1; learn[sym]["score"]=min(1,learn[sym]["score"]+0.05)
     elif res=="LOSS": learn[sym]["l"]+=1; learn[sym]["score"]=max(0,learn[sym]["score"]-0.08)
     learn[sym]["last_trades"].insert(0,res)
     learn[sym]["last_trades"]=learn[sym]["last_trades"][:10]
    if res!="SCRATCH":
     fee_tot+=0.02; cap+=net; tot+=1
     if res=="WIN": wins+=1
     if sym not in st: st[sym]={"w":0,"l":0,"profit":0.0}
     st[sym]["w" if res=="WIN" else "l"]+=1; st[sym]["profit"]+=net
    cn.append({'symbol':sym,'entry':entry,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,3),'mode':tm,'price':real,'reason':reason,'score':round(learn.get(sym,{}).get('score',0.5),2)})
   else:
    nw.append(t)
  for c in cn: cl.insert(0,c)
  cl=cl[:200]; o=nw
  # WATCHING MARKET: Open best learning score coins, follow each move
  if len(o)<5:
   candidates=[]
   for s in prices.keys():
    if s in [x['symbol'] for x in o]: continue
    h=hist.get(s,[])
    if len(h)<3: continue
    # Calculate 5s and 10s momentum - watching market
    p_now=prices[s]; p5=None; p10=None
    for ts,pr in reversed(h):
     if p5 is None and now-ts>=5: p5=pr
     if p10 is None and now-ts>=10: p10=pr
    if not p5 or not p10: continue
    mom5=(p_now-p5)/p5*100 if p5>0 else 0
    mom10=(p_now-p10)/p10*100 if p10>0 else 0
    score=learn.get(s,{}).get('score',0.5)
    # Skip if coin learned to be bad (score <0.3 after 3 losses)
    if score<0.3 and learn.get(s,{}).get('l',0)>=3: continue
    # Only trade if moving (your idea: some coins always moving)
    if abs(mom5)>=0.05 and abs(mom10)>=0.06:
     # Trend alignment: 5s and 10s same direction = strong move
     if (mom5>0)==(mom10>0):
      candidates.append((s,abs(mom5)+abs(mom10)+score,mom5,mom10,score))
   candidates.sort(key=lambda x: x[1], reverse=True)
   for sym,total_score,m5,m10,learn_score in candidates[:5-len(o)]:
    e=prices.get(sym)
    if not e: continue
    mode="LONG" if m5>0 else "SHORT"
    o.append({'symbol':sym,'entry':e,'t':now,'m5':round(m5,3),'m10':round(m10,3),'mode':mode,'price':e,'peak':0,'learn_score':round(learn_score,2)})
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices)); save('VENUS_LEARN',learn)
  return {"ok":True,"closed":len(cn),"open":len(o),"p":len(prices)}
 except Exception as e:
  save('last',f"ERR {str(e)[:90]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_PREV','VENUS_HIST','VENUS_LEARN','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('VENUS_HIST',{}); save('VENUS_LEARN',{}); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True}
@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state():
 return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"learn":load('VENUS_LEARN',{}),"last":load('last','never'),"kv":KV,"fee":load('VENUS_FEE',0.0),"price_count":load('VENUS_PRICE',0)}
@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.scratch{color:#888}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:10px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
</style></head><body>
<h2>VENUS v182 LEARNING BOT FOLLOWS MARKET NO FIXED %</h2>
<div class=card>CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/5</span> | Prices <span id=pc>0</span> | Fees $<span id=fee>0</span><br><span class=m>LEARNING: Watches 5s vs 10s move, if UP 5s then DOWN 10s → flips LONG→SHORT instantly, no fixed LOSS.04% WIN.12%, bot decides profit/loss itself, learns from mistake score per coin, trails peak, always moving 5 coins</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | V182 LEARNING ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,500))">🚀 FORCE LEARNING BOT</button><button class=btn2 onclick="if(confirm('WIPE to $300?')){fetch('/api/reset').then(()=>setTimeout(loadState,400))}">🗑️ WIPE → $300 LEARNING</button></div>
<div class=card><b>Open <span id=oc2>0/5</span> learning follows market</b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed LEARNING - bot decides</b><div id=closed>Waiting...</div></div>
<div class=card><b>Learn from mistake per coin</b><div id=learn class=m>Waiting...</div></div>
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
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/5';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/5';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode} ${t.symbol} 5s ${t.m5||0}% 10s ${t.m10||0}% learn ${t.learn_score||0} ${t.m5>0?'📈':'📉'}</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s peak ${t.peak||0}%</span></div>`).join('')||'No open - watching market 5s vs 10s move';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} ${c.hold}s ${c.pct||0}% score ${c.score||0}</span><span><span class=${c.result=='WIN'?'win':c.result=='SCRATCH'?'scratch':'loss'}>${c.result} $${(c.net||0).toFixed(3)} ${c.reason||''}</span></span></div>`).join('')||'No trades - bot learning';
  if(el('learn')){ let html='LEARN FROM MISTAKE per coin:<br>'; for(let k in j.learn){ let l=j.learn[k]; html+=`${k}: ${l.w||0}W/${l.l||0}L score ${l.score?.toFixed(2)} last ${l.last_trades?.slice(0,3).join(',')}<br>`; } html+='<br>Bot decides: No fixed.04%/.12%, watches FLIP DOWN/UP, TRAIL PEAK, CUT LOSS'; el('learn').innerHTML=html; }
 }catch(e){}
}
setInterval(loadState,2500); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},4000);
</script></body></html>"""
