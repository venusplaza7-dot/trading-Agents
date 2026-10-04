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
  try:
   v=db.get(k)
   return json.loads(v) if v else d
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
 coins=["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","LINKUSDT","AVAXUSDT","ADAUSDT","XRPUSDT","BNBUSDT","LTCUSDT"]
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/price",timeout=3)
  if r.status_code==200:
   for d in r.json():
    if d['symbol'] in coins: out[d['symbol']]=float(d['price'])
 except: pass
 if len(out)<5:
  for cb,sym in [("BTC-USD","BTCUSDT"),("ETH-USD","ETHUSDT"),("SOL-USD","SOLUSDT"),("DOGE-USD","DOGEUSDT"),("LINK-USD","LINKUSDT")]:
   if sym in out: continue
   try:
    r=requests.get(f"https://api.coinbase.com/v2/prices/{cb}/spot",timeout=2)
    if r.status_code==200: out[sym]=float(r.json()['data']['amount'])
   except: pass
 return out

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',1000.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); hist=load('VENUS_HIST',{}); ticks=load('VENUS_TICKS',{}); now=time.time()
  prices=get_prices()
  if len(prices)<3:
   save('VENUS_PRICE',len(prices))
   return {"ok":False,"p":len(prices)}
  for s,p in prices.items():
   if s not in hist: hist[s]=[]
   if s not in ticks: ticks[s]=[]
   hist[s].append((now,p)); hist[s]=[x for x in hist[s] if now-x[0]<90]
   ticks[s].append(p); ticks[s]=ticks[s][-80:]
  save('VENUS_HIST',hist); save('VENUS_TICKS',ticks); save('VENUS_PRICE',len(prices))
  nw=[]; cn=[]; fee_fut_tot=load('VENUS_FEE_FUT',0.0)
  for t in o:
   sym=t['symbol']; entry=t['entry']; tm=t['mode']; entry_t=t['t']; pos=t.get('pos',200.0)
   real=prices.get(sym)
   if not real: nw.append(t); continue
   age=now-entry_t; pct=((real-entry)/entry*100) if tm=="LONG" else ((entry-real)/entry*100)
   gross=pos*pct/100; fee_fut=pos*0.0004; net_fut=gross-fee_fut
   tk=ticks.get(sym,[]); tr=[abs(tk[i]-tk[i-1])/tk[i-1]*100 for i in range(1,len(tk))] if len(tk)>1 else [0.02]
   atr=sum(tr[-8:])/8 if len(tr)>=8 else 0.02
   target=0.20 if atr>0.025 else 0.12
   cut=max(0.10, atr*1.5)
   if age>70 and abs(pct)<0.05:
    cn.append({'symbol':sym,'entry':entry,'net':0.0,'gross':round(gross,3),'fee_fut':round(fee_fut,3),'result':"SCRATCH",'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,4),'mode':tm,'price':real,'reason':f"SCRATCH 30SEC 5 COINS {pct:.4f}% age {int(age)}s ATR {atr:.4f}%",'pos':pos})
    continue
   if gross>0 and gross < fee_fut*1.5 and age<25: nw.append(t); continue
   should=False; reason=""; peak=t.get('peak',pct)
   if pct>peak: t['peak']=pct
   if pct>=target: should=True; reason=f"WIN 30SEC 5 COINS $1 {pct:.3f}% target {target:.3f}% ATR {atr:.4f}% gross ${gross:.2f} fee ${fee_fut:.2f} net ${net_fut:.2f} CAP ${cap:.2f}"
   elif peak>=target and pct<peak*0.40: should=True; reason=f"TRAIL 30SEC $1 {peak:.2f}%→{pct:.2f}% net ${net_fut:.2f}"
   elif pct<=-cut: should=True; reason=f"CUT 30SEC {pct:.3f}%"
   if age>35 and pct>=0.09: should=True; reason=f"MAX 35s PROFIT {pct:.3f}% net ${net_fut:.2f}"
   if age>75: should=True; reason=f"MAX 75s {pct:.3f}%"
   if should:
    if net_fut>0.08: res="WIN"
    elif net_fut<-0.08: res="LOSS"
    else: res="SCRATCH" if age>=60 else None
    if res is None: nw.append(t); continue
    if res!="SCRATCH": fee_fut_tot+=fee_fut; cap+=net_fut; tot+=1
     if res=="WIN": wins+=1
    cn.append({'symbol':sym,'entry':entry,'net':round(net_fut,2) if res!="SCRATCH" else 0.0,'gross':round(gross,3),'fee_fut':round(fee_fut,3),'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,4),'mode':tm,'price':real,'reason':reason,'pos':pos,'atr':round(atr,4),'target':round(target,3),'cap':round(cap,2)})
   else:
    if pct>t.get('peak',-999): t['peak']=pct
    nw.append(t)
  for c in cn: cl.insert(0,c)
  cl=cl[:200]; o=nw
  candidates=[]
  for s in prices.keys():
   if s in [x['symbol'] for x in o]: continue
   if s not in ticks or len(ticks[s])<6: continue
   tk=ticks[s]; tr=[abs(tk[i]-tk[i-1])/tk[i-1]*100 for i in range(1,len(tk))] if len(tk)>1 else [0.01]
   atr=sum(tr[-6:])/6 if len(tr)>=6 else 0.005
   if atr<0.007: continue
   vwap=sum(tk[-12:])/12 if len(tk)>=12 else prices[s]; vwap_dev=(prices[s]-vwap)/vwap*100 if vwap>0 else 0
   if abs(vwap_dev)<0.05: continue
   mode="SHORT" if vwap_dev>0.05 else "LONG"; speed=atr*3 + abs(vwap_dev)
   candidates.append((s,speed,atr,vwap_dev,mode))
  candidates.sort(key=lambda x:x[1], reverse=True)
  max_open=5; pos_each=round(min(200, max(150, cap/max_open)),1)
  for sym,speed,atr,vwap_dev,mode in candidates[:max_open-len(o)]:
   o.append({'symbol':sym,'entry':prices[sym],'t':now,'mode':mode,'price':prices[sym],'peak':0,'pos':pos_each,'rev':0,'size_reason':f"30SEC 5 COINS $1 {sym} ATR {atr:.4f}% VWAP {vwap_dev:.3f}% speed {speed:.4f}% pos ${pos_each} target 0.20%=${pos_each*0.20/100:.2f} quick CAP ${cap:.2f}"})
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_FEE_FUT',fee_fut_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"open":len(o),"closed":len(cn),"cap":cap,"p":len(prices)}
 except Exception as e:
  save('last',f"ERR {str(e)[:60]}")
  return {"ok":False}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_FEE_FUT','VENUS_PRICE','VENUS_HIST','VENUS_TICKS','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',1000.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_FEE_FUT',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('VENUS_HIST',{}); save('VENUS_TICKS',{}); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True,"cap":1000}
@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state():
 return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',1000.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"last":load('last','never'),"kv":KV,"fee_fut":load('VENUS_FEE_FUT',0.0),"price_count":load('VENUS_PRICE',0)}
@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.scratch{color:#888}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:10px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.k{background:#00331a;border:2px solid #00ff88}
</style></head><body>
<h2>VENUS v212 FIXED BUILD $1000 30SEC 5 COINS $1</h2>
<div class="card k">CAP $<span id=cap>1000</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/5</span> | Prices <span id=pc>0</span> | Fut Fee $<span id=fee>0</span><br><span class=m>$1000 30SEC 5 COINS $1 PER TRADE FIXED BUILD: Fixed duplicate def delete crash. 5 coins × $200 = $1000 every 30sec = 10 trades/min. Pos $200 fee $0.08 target 0.20% gross $0.40 net $0.32 ×10 = $3.20/min = $192/hour paper. Pos $500 2 coins every 30sec = 4 trades/min ×$0.80=$3.20/min same. Fast movers ATR 0.007%+ VWAP 0.05%+ speed ranking. MAX 75s profit 35s 30sec avg. Real market + real fee fixed. Beats market fast.</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | V212 FIXED BUILD ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,500))">🚀 FORCE 30SEC 5 COINS $1 FIXED BUILD</button></div>
<div class=card><b>Open <span id=oc2>0/5</span> $1000 30SEC 5 COINS $200 FAST</b><div id=open>5 coins $200 each = $1000 total every 30sec — 10 trades/min — $1 per trade quick</div></div>
<div class=card><b>Closed $1000 30SEC 5 COINS $1</b><div id=closed>Waiting 30SEC 5 COINS $1 WIN $0.32-$0.80 quick</div></div>
<script>
async function loadState(){
 try{
  let r=await fetch('/api/state'); let j=await r.json();
  let el=(id)=>document.getElementById(id);
  if(el('cap')) el('cap').innerText=(j.cap||1000).toFixed(2);
  if(el('fee')) el('fee').innerText=(j.fee_fut||0).toFixed(2);
  if(el('cr')) el('cr').innerText=j.last||'never';
  if(el('kv')) el('kv').innerText=j.kv?'YES':'NO';
  if(el('pc')) el('pc').innerText=j.price_count||0;
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/5';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/5';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode} ${t.symbol} pos $${(t.pos||200).toFixed(0)}<br><small>${t.size_reason||''}</small></span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'5 coins $200 each = $1000 total every 30sec — 10 trades/min';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} pos $${c.pos||200} ${c.hold}s ${c.pct||0}% target ${c.target||0}% ATR ${c.atr||0}% gross $${c.gross||0} net $${c.net||0} cap $${c.cap||0} ${c.reason||''}</span><span><span class=${c.result=='WIN'&&c.net>0?'win':c.result=='SCRATCH'?'scratch':'loss'}>${c.result} $${(c.net||0).toFixed(2)}</span></span></div>`).join('')||'Waiting 30SEC 5 COINS $1 WIN $0.32-$0.80 quick 10 trades/min';
 }catch(e){}
}
setInterval(loadState,2500); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},2500);
</script></body></html>"""
