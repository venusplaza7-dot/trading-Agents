from flask import Flask
import json, random, time
from datetime import datetime

app = Flask(__name__)

# KV try
try:
    from upstash_redis import Redis
    r = Redis.from_env()
    def get(k,d):
        try:
            v=r.get(k)
            return json.loads(v) if v else d
        except: return d
    def set(k,v):
        try: r.set(k, json.dumps(v))
        except: pass
    KV=True
except:
    M={}
    def get(k,d): return M.get(k,d)
    def set(k,v): M[k]=v
    KV=False

@app.route('/api/cron')
def cron():
    o=get('o',[])
    o=[t for t in o if time.time()-t['at']<120]
    if len(o)<10:
        o.append({'symbol':random.choice(['BONKUSDT','FLOKIUSDT','MEMEUSDT','PEPEUSDT']),'tier':'ULTRA','score':8.9,'conf':85,'at':time.time()})
    set('o',o)
    set('last',datetime.now().isoformat())
    return {'ok':True,'kv':KV,'open':len(o)}

@app.route('/api/state')
def state():
    return {'open':get('o',[]),'last':get('last','never'),'kv':KV,'cap':0}

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def home(path):
    return '''<!DOCTYPE html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<style>body{background:#111;color:#fff;font-family:Arial;padding:12px}.card{background:#222;border-radius:12px;padding:12px;margin:8px 0}.g{color:#0f0}.btn{background:#0f0;color:#000;padding:10px;border-radius:8px;text-align:center;font-weight:bold}</style></head><body>
<h3>VENUS v123 BEST LOGICAL $0.30 TIERED</h3>
<div class=card>CAP $300 | DAILY $0 | GOAL $50 | Cron: <span id=c>never</span> | KV: <span id=k>...</span></div>
<div class=card><div class=btn>AUTO ON</div><div id=s>Loading...</div></div>
<div class=card><b>Open Trades</b> <span id=oc>0/10</span><div id=o>Waiting...</div></div>
<div class=card>12 Coins BEST - ULTRA BONK PEPE SHIB FLOKI 1.5% TP 1-3m BEST</div>
<script>
async function R(){let j=await (await fetch('/api/state')).json();document.getElementById('k').innerText=j.kv?'CONNECTED ✅':'NO';document.getElementById('c').innerText=j.last;document.getElementById('oc').innerText=j.open.length+'/10 open';document.getElementById('o').innerHTML=j.open.map(t=>t.symbol+' ULTRA Score '+t.score).join('<br>')||'Waiting score>4.0';document.getElementById('s').innerText='OK '+j.open.length+' trades | Cron '+j.last}
setInterval(R,3000);R();setInterval(()=>fetch('/api/cron'),15000);
</script></body></html>'''
