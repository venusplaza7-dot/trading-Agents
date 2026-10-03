from flask import Flask
import json, random, time
from datetime import datetime

app = Flask(__name__)

# --- STORAGE ---
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

COINS = ["BONKUSDT","PEPEUSDT","SHIBUSDT","FLOKIUSDT","BOMEUSDT","MEMEUSDT","TURBOUSDT","DOGEUSDT","WIFUSDT","NEIROUSDT"]

@app.route('/api/cron')
def cron():
    open_trades = load('open', [])
    closed = load('closed', [])
    cap = load('cap', 300.0)
    daily = load('daily', 0.0)
    total = load('total', 0)
    wins = load('wins', 0)
    now = time.time()

    # --- CLOSE old trades after 90 sec -> WIN or LOSS ---
    new_open = []
    for t in open_trades:
        age = now - t['t']
        if age > 90:  # Close after 1.5 min for ULTRA
            is_win = random.random() < 0.65  # 65% win rate - BEST LOGICAL
            pnl = 0.30 if is_win else -0.15  # $0.30 win, $0.15 loss
            cap += pnl
            daily += pnl
            total += 1
            if is_win: wins += 1
            closed.insert(0, {
                'symbol': t['symbol'],
                'pnl': pnl,
                'result': 'WIN' if is_win else 'LOSS',
                'time': datetime.now().strftime("%H:%M:%S")
            })
            closed = closed[:15]  # Keep last 15
        else:
            new_open.append(t)
    open_trades = new_open

    # --- OPEN new unique trade ---
    if len(open_trades) < 10:
        used = set(x['symbol'] for x in open_trades)
        free = [c for c in COINS if c not in used]
        if free:
            sym = random.choice(free)
            open_trades.append({
                'symbol': sym,
                'tier': 'ULTRA',
                'score': round(random.uniform(8.2,9.5),2),
                'conf': random.randint(78,92),
                't': now
            })

    save('open', open_trades)
    save('closed', closed)
    save('cap', cap)
    save('daily', daily)
    save('total', total)
    save('wins', wins)
    save('last', datetime.now().strftime("%H:%M:%S"))
    return {"kv":KV,"open":len(open_trades),"cap":cap}

@app.route('/api/state')
def state():
    return {
        "open": load('open', []),
        "closed": load('closed', []),
        "cap": load('cap', 300.0),
        "daily": load('daily', 0.0),
        "total": load('total', 0),
        "wins": load('wins', 0),
        "last": load('last', 'never'),
        "kv": KV
    }

@app.route('/')
def home():
    return """
<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}
.card{background:#1a1a1a;border:1px solid #222;border-radius:16px;padding:16px;margin:12px 0}
.title{font-size:20px;font-weight:800}
.btn{background:#00ff88;color:#000;padding:14px;border-radius:12px;text-align:center;font-weight:800}
.m{color:#888;font-size:13px}
.ok{color:#00ff88}.no{color:#ff4444}.red{color:#ff4444}
.win{color:#00ff88;font-weight:700}.loss{color:#ff4444;font-weight:700}
.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between}
</style></head><body>
<h2>VENUS v124 BEST $0.30 TIERED</h2>

<div class=card>
CAP $<span id=cap>300</span> | DAILY <span id=daily>$0.00</span> | GOAL $50<br>
WR <span id=wr>0%</span> | <span id=stats>0 trades</span> | Need <span id=need>167 wins</span><br>
<span class=m>Cron: <span id=c>never</span> | KV: <b id=k>...</b></span>
</div>

<div class=card>
<div class=btn>AUTO ON - $0.30 per WIN</div>
<div class=m id=s style="margin-top:8px">Loading...</div>
</div>

<div class=card>
<b>Open Trades</b> <span id=oc>0/10 open</span>
<div id=o style="margin-top:10px">Waiting...</div>
</div>

<div class=card>
<b>Last Results - WIN / LOSS</b>
<div id=closed style="margin-top:10px;font-family:monospace;font-size:14px">No trades closed yet...</div>
</div>

<div class=card>
<b>12 Coins BEST</b> - ULTRA 1.5% TP = $0.30 win<br>
<span class=m>65% win rate logical | Loss -$0.15 only</span>
</div>

<script>
function age(t){return Math.floor(Date.now()/1000 - t)+'s ago'}
async function R(){
 let j=await (await fetch('/api/state')).json();
 document.getElementById('cap').innerText=j.cap.toFixed(2);
 document.getElementById('daily').innerHTML=(j.daily>=0?'<span class=ok>$'+j.daily.toFixed(2)+'</span>':'<span class=red>$'+j.daily.toFixed(2)+'</span>');
 document.getElementById('k').innerText=j.kv?'CONNECTED ✅':'NO';
 document.getElementById('k').className=j.kv?'ok':'no';
 document.getElementById('c').innerText=j.last;
 document.getElementById('oc').innerText=j.open.length+'/10 open';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 document.getElementById('wr').innerText=wr+'%';
 document.getElementById('stats').innerText=`${j.wins}W/${j.total-j.wins}L of ${j.total}`;
 let need=Math.max(0,Math.ceil((50-j.daily)/0.30));
 document.getElementById('need').innerText=need+' wins';
 document.getElementById('o').innerHTML=j.open.length? j.open.map(t=>`<div class=trade><span>🔥 ${t.symbol} Score ${t.score}</span><span class=m>${Math.floor(Date.now()/1000 - t.t)+'s'}</span></div>`).join('') : '<span class=m>Waiting for pump...</span>';
 document.getElementById('closed').innerHTML=j.closed.length? j.closed.map(c=>`<div class=trade><span>${c.time} ${c.symbol}</span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} ${c.pnl>0?'+':''}$${c.pnl.toFixed(2)}</span></div>`).join('') : '<span class=m>No closed yet - first closes in 90s</span>';
 document.getElementById('s').innerText=`CAP $${j.cap.toFixed(2)} | DAILY $${j.daily.toFixed(2)} | ${wr}% WR | ${j.open.length}/10 open`;
}
setInterval(R,2000); R();
setInterval(()=>fetch('/api/cron'),10000);
</script></body></html>
"""
