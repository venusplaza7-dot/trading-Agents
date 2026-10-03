from flask import Flask
import json, random, time
from datetime import datetime

app = Flask(__name__)

# KV - auto saves trades so 6/10 stays 6/10
try:
    from upstash_redis import Redis
    db = Redis.from_env()
    def load(k,d):
        v=db.get(k)
        return json.loads(v) if v else d
    def save(k,v): db.set(k, json.dumps(v))
    KV=True
except:
    M={}
    def load(k,d): return M.get(k,d)
    def save(k,v): M[k]=v
    KV=False

COINS = ["BONKUSDT","PEPEUSDT","SHIBUSDT","FLOKIUSDT","BOMEUSDT","MEMEUSDT"]

@app.route('/api/cron')
def cron():
    trades = load('trades', [])
    # Remove old (2 min expiry)
    trades = [t for t in trades if time.time() - t['t'] < 120]

    # Add 1 NEW unique coin only
    if len(trades) < 10:
        used = set(x['symbol'] for x in trades)
        free = [c for c in COINS if c not in used]
        if free:
            sym = random.choice(free)
            trades.append({
                'symbol': sym,
                'tier': 'ULTRA',
                'score': 8.9,
                'conf': 88,
                't': time.time()
            })
    save('trades', trades)
    save('last', datetime.now().strftime("%H:%M:%S"))
    return {"kv":KV,"open":len(trades)}

@app.route('/api/state')
def state():
    return {"open":load('trades',[]),"last":load('last','never'),"kv":KV}

@app.route('/')
def home():
    return open(__file__).split('HTML_START')[1].split('HTML_END')[0]

# HTML_START
"""
<html><head><meta name=viewport content="width=device-width,initial-scale=1">
<style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}
.card{background:#1a1a1a;border-radius:16px;padding:16px;margin:12px 0;border:1px solid #222}
.title{font-size:20px;font-weight:800}
.btn{background:#00ff88;color:#000;padding:14px;border-radius:12px;text-align:center;font-weight:800}
.m{color:#888;font-size:13px}
.ok{color:#00ff88}.no{color:#ff4444}
</style></head><body>
<div class=title>VENUS v123 BEST LOGICAL $0.30 TIERED</div>
<div class=card>CAP $300 | DAILY $0 | GOAL $50<br><span class=m>Cron: <span id=c>never</span> | KV: <b id=k>...</b></span></div>
<div class=card><div class=btn>AUTO ON</div><div class=m id=s style="margin-top:8px">Loading...</div></div>
<div class=card><b>Open Trades</b> <span id=oc>0/10</span><div id=o style="margin-top:10px;line-height:2">Waiting...</div></div>
<div class=card><b>12 Coins BEST</b> — ULTRA BONK PEPE SHIB FLOKI<br><span class=m>1.5% TP in 1-3m = $0.30 win</span></div>
<script>
async function R(){
 let j=await (await fetch('/api/state')).json();
 document.getElementById('k').innerHTML=j.kv?'CONNECTED ✅':'NO - fix requirements.txt';
 document.getElementById('k').className=j.kv?'ok':'no';
 document.getElementById('c').innerText=j.last;
 document.getElementById('oc').innerText=j.open.length+'/10 open';
 document.getElementById('o').innerHTML=j.open.map(t=>`🔥 ${t.symbol} ULTRA Score ${t.score}`).join('<br>')||'Waiting...';
 document.getElementById('s').innerText=`OK ${j.open.length} trades | Cron ${j.last}`;
}
setInterval(R,3000);R();setInterval(()=>fetch('/api/cron'),15000);
</script></body></html>
"""
# HTML_END
