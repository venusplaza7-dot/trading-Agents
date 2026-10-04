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
 ids="pepe,bonk,dogwifcoin,floki,dogecoin,shiba-inu,brett,popcat,mog-coin,turbo,fartcoin,cat-in-a-dogs-world,pudgy-penguins,official-trump,notcoin,worldcoin-wld,bittensor,goatseus-maximus,virtual-protocol,fetch-ai,solana,pyth-network"
 mp={"pepe":"PEPEUSDT","bonk":"BONKUSDT","dogwifcoin":"WIFUSDT","floki":"FLOKIUSDT","dogecoin":"DOGEUSDT","shiba-inu":"SHIBUSDT","brett":"BRETTUSDT","popcat":"POPCATUSDT","mog-coin":"MOGUSDT","turbo":"TURBOUSDT","fartcoin":"FARTCOINUSDT","cat-in-a-dogs-world":"MEWUSDT","pudgy-penguins":"PENGUUSDT","official-trump":"TRUMPUSDT","notcoin":"NOTUSDT","worldcoin-wld":"WLDUSDT","bittensor":"TAOUSDT","goatseus-maximus":"GOATUSDT","virtual-protocol":"VIRTUALUSDT","fetch-ai":"FETUSDT","solana":"SOLUSDT","pyth-network":"PYTHUSDT"}
 try:
  r=requests.get(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&price_change_percentage=24h&per_page=30&page=1",timeout=7)
  if r.status_code==200:
   data=r.json()
   out={}; m24={}
   for c in data:
    sym=mp.get(c['id'])
    if sym:
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
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); prev=load('VENUS_PREV',{}); banned=load('VENUS_BANNED',{}); stop_until=load('VENUS_STOP_UNTIL',0); now=time.time()
  prices,m24=get_prices()
  if not prices:
   return {"ok":False,"reason":"no_prices"}

  # REAL momentum from OUR prev - fixes Mom 0% bug
  mom={}
  for s,p in prices.items():
   if s in prev and prev[s]>0:
    mom[s]=(p-prev[s])/prev[s]*100
   else:
    mom[s]=0
  save('VENUS_PREV',prices)

  avg_vol=sum(abs(v) for v in mom.values())/max(1,len(mom))
  recent=cl[:30]
  recent_wr=(sum(1 for x in recent if x.get('result')=='WIN')/len(recent)*100) if len(recent)>=10 else 50

  # LEARNING 1: If recent WR <25% after 30 trades -> STOP 2 hours
  if len(recent)>=20 and recent_wr < 25:
   save('VENUS_STOP_UNTIL', now + 7200)
   save('VENUS_MODE','STOPPED_LOW_WR')
   return {"ok":True,"stopped":"low_wr","recent_wr":recent_wr}

  # LEARNING 2: If market flat vol <0.04% -> STOP 1 hour
  if avg_vol < 0.04 and tot>20:
   save('VENUS_STOP_UNTIL', now + 3600)
   save('VENUS_MODE','STOPPED_FLAT')
   return {"ok":True,"stopped":"flat","vol":avg_vol}

  if now < stop_until:
   save('VENUS_MODE',f"WAITING_{int((stop_until-now)/60)}m")
   return {"ok":True,"waiting":int(stop_until-now)}

  # Close open trades
  nw=[]
  for t in o:
   real=prices.get(t['symbol'])
   if not real:
    if now-t.get('t',now)>90:
     tot+=1; fee_tot+=0.20; cap+=-0.50
     if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0,"last_win":0}
     st[t['symbol']]["l"]+=1; st[t['symbol']]["profit"]+=-0.50
     if st[t['symbol']]["w"]==0 and st[t['symbol']]["l"]>=2:
      banned[t['symbol']]=now+86400*365 # permanent ban
     cl.insert(0,{'symbol':t['symbol'],'net':-0.50,'result':'LOSS','time':datetime.now().strftime("%H:%M:%S"),'hold':int(now-t.get('t',now)),'mode':t.get('mode','SHORT')})
    else:
     nw.append(t)
    continue
   age=now-t.get('t',now); res=None
   tm=t.get('mode','SHORT')
   if tm=="SHORT":
    if real<=t['entry']*0.993: res="WIN" # drop 0.7%
    elif real>=t['entry']*1.006: res="LOSS" # pump 0.6%
    elif age>75: res="WIN" if real<=t['entry']*0.999 else "LOSS"
   else:
    if real>=t['entry']*1.007: res="WIN"
    elif real<=t['entry']*0.994: res="LOSS"
    elif age>75: res="WIN" if real>=t['entry']*1.001 else "LOSS"
   if res:
    fee=0.20
    gw=0.35; gl=0.30
    gross=gw if res=="WIN" else -gl
    net=gross-fee if res=="WIN" else -gl-fee # WIN $0.15 LOSS $-0.50
    fee_tot+=fee; cap+=net; tot+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0,"last_win":0}
    st[t['symbol']]["w" if res=="WIN" else "l"]+=1
    st[t['symbol']]["profit"]+=net
    if res=="WIN": st[t['symbol']]["last_win"]=now
    else:
     # LEARNING 3: Ban 0W/2L permanent
     if st[t['symbol']]["w"]==0 and st[t['symbol']]["l"]>=2:
      banned[t['symbol']]=now+86400*365
    cl.insert(0,{'symbol':t['symbol'],'gross':gross,'fee':fee,'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'m':round(mom.get(t['symbol'],0),3),'m24':round(m24.get(t['symbol'],0),1),'mode':tm})
    cl=cl[:150]
   else:
    nw.append(t)
  o=nw

  # LEARNING 4: Trade 2 coins ONLY if BEST coin exists, else 0 coins (wait)
  if len(o)<2:
   used=set(x.get('symbol') for x in o)
   def wr(s): dd=st.get(s,{"w":1,"l":1}); return dd["w"]/max(1,dd["w"]+dd["l"])
   def profit(s): return st.get(s,{}).get("profit",0)
   def is_good(s):
    if s in banned and banned[s]>now: return False
    st_s=st.get(s,{"w":0,"l":0})
    if st_s["w"]==0 and st_s["l"]>=2: return False
    if st_s["w"]==0 and st_s["l"]>=1 and profit(s)<-0.8: return False
    return True

   pool=[s for s in prices.keys() if s not in used and is_good(s)]
   # For SHORT: need real pump >0.08% to short (mean reversion)
   # For LONG: need real pump >0.05% to follow (momentum)
   # At flat 4am, only SHORT good pumps
   good=[]
   for s in pool:
    m=mom.get(s,0)
    if m>0.08: # strong pump to short for 90% WR
     good.append(s)
   good.sort(key=lambda x: mom.get(x,0), reverse=True)

   # If no good pump, WAIT - don't force trade (this is the $180 lesson!)
   if good:
    top=good[:2]
    for _ in range(2-len(o)):
     if not top: break
     sym=top[0]
     e=prices.get(sym)
     if e:
      o.append({'symbol':sym,'entry':e,'t':now,'wr':int(wr(sym)*100),'m':round(mom.get(sym,0),3),'m24':round(m24.get(sym,0),1),'mode':'SHORT','score':round(mom.get(sym,0),3)})
      top.pop(0)
     else:
      top.pop(0)
   # else: trade 0 - waiting is winning!

  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices)); save('VENUS_BANNED',banned)
  save('VENUS_MODE','SHORT_SELECTIVE' if good else 'WAITING_BEST')
  return {"ok":True,"prices":len(prices),"open":len(o),"good":len(good) if 'good' in locals() else 0,"vol":avg_vol,"
